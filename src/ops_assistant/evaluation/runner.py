"""Run the evaluation sets and save every raw result.

Each run writes to its own folder under eval/results:

* ``run.json``: what was run (settings, model, corpus fingerprint, case-file hash, commit).
* ``cases.jsonl`` or ``per_case.csv``: one raw record per case or per case and configuration.
* ``summary.md``: the tables, regenerated from the raw records by report.py.

Raw records are kept so the scoring can be re-read and checked without re-running.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import platform
import statistics
import subprocess
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import numpy as np

from ops_assistant.answer import AnswerResult, InvalidQuestion
from ops_assistant.chunking import Strategy, chunk_corpus
from ops_assistant.config import RetrievalMode, Settings
from ops_assistant.corpus import load_effective_corpus
from ops_assistant.evaluation.cases import (
    CaseSet,
    EvalCase,
    cases_path,
    check_freeze,
    file_hash,
    load_cases,
)
from ops_assistant.evaluation.scoring import score_retrieval
from ops_assistant.llm.base import Embedder, ProviderError, TextGenerator
from ops_assistant.retrieval import MemoEmbedder, build_retriever, needs_embeddings
from ops_assistant.service import build_pipeline

logger = logging.getLogger(__name__)

# Errors that will repeat on every case, so the run stops instead of spending more calls.
FATAL_CATEGORIES = {"provider_not_configured", "provider_auth_failed", "provider_quota_exceeded"}


def _git_commit(root: Path) -> dict[str, str | bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return {"commit": commit, "uncommitted_changes": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "uncommitted_changes": True}


def _versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in ("ops-assistant", "openai", "numpy"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def _call_stats(embedder: MemoEmbedder | None) -> dict[str, float | int] | None:
    """Latency of the real embedding calls made by the experiment, one per question."""
    if embedder is None or not embedder.call_ms:
        return None
    times = sorted(embedder.call_ms)
    return {
        "calls": len(times),
        "median_ms": round(statistics.median(times), 1),
        "p95_ms": round(float(np.percentile(times, 95)), 1),
        "max_ms": round(times[-1], 1),
        "retries": embedder.retries,
        "tokens": embedder.tokens_spent,
    }


def _run_dir(results_dir: Path, kind: str, case_set: str, label: str) -> Path:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = results_dir / f"{stamp}_{kind}_{case_set}_{label}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _load_set(settings: Settings, case_set: CaseSet) -> tuple[list[EvalCase], str]:
    path = cases_path(settings.root / "eval", case_set)
    digest = check_freeze(path) if case_set == "frozen" else file_hash(path)
    return load_cases(path), digest


def record_from_result(case: EvalCase, result: AnswerResult) -> dict:
    return {
        "id": case.id,
        "status": "ok",
        "outcome": result.outcome,
        "answer": result.answer,
        "conflict_note": result.conflict_note,
        "citations": [c.chunk_id for c in result.citations],
        "cited_text": {c.chunk_id: c.text for c in result.citations},
        "cited_by_model": result.cited_by_model,
        "removed_citations": result.invalid_citations,
        "retrieved": [
            {
                "id": r.chunk.chunk_id,
                "rank": r.rank,
                "score": r.score,
                "sections": sorted(r.chunk.evidence_keys),
            }
            for r in result.retrieved
        ],
        "generation_skipped": result.generation_skipped,
        "model": result.model,
        "input_tokens": result.usage.input_tokens,
        "cached_input_tokens": result.usage.cached_input_tokens,
        "output_tokens": result.usage.output_tokens,
        "reasoning_tokens": result.usage.reasoning_tokens,
        "embedding_tokens": result.embedding_tokens,
        "cost_usd": result.cost_usd,
        "retrieval_ms": result.timings.retrieval_ms,
        "generation_ms": result.timings.generation_ms,
        "total_ms": result.timings.total_ms,
        "provider_retries": result.provider_retries,
        "provider_request_id": result.provider_request_id,
        "warnings": result.warnings,
    }


def error_record(
    case: EvalCase, category: str, stage: str, message: str, elapsed_ms: float
) -> dict:
    return {
        "id": case.id,
        "status": "error",
        "error_category": category,
        "error_stage": stage,
        "error_message": message,
        "total_ms": elapsed_ms,
    }


@dataclass(frozen=True)
class AnswerRunOptions:
    case_set: CaseSet
    mode: RetrievalMode
    limit: int | None = None
    case_ids: tuple[str, ...] = ()


def run_answers(
    settings: Settings,
    options: AnswerRunOptions,
    generator: TextGenerator | None = None,
    embedder: Embedder | None = None,
    results_dir: Path | None = None,
) -> Path:
    cases, digest = _load_set(settings, options.case_set)
    if options.case_ids:
        cases = [c for c in cases if c.id in options.case_ids]
    if options.limit:
        cases = cases[: options.limit]

    settings = settings.with_overrides(retrieval={"mode": options.mode})
    # Questions are embedded live, as in the service, so retrieval times include the API call.
    pipeline = build_pipeline(settings, generator, embedder, options.mode)

    results_dir = results_dir or settings.root / "eval" / "results"
    run_dir = _run_dir(results_dir, "answers", options.case_set, options.mode)
    records: list[dict] = []
    for case in cases:
        started = time.perf_counter()
        try:
            record = record_from_result(case, pipeline.service.ask(case.question))
        except ProviderError as error:
            elapsed = (time.perf_counter() - started) * 1000
            record = error_record(case, error.category, error.stage, str(error), elapsed)
        except InvalidQuestion as error:
            elapsed = (time.perf_counter() - started) * 1000
            record = error_record(case, error.category, "request", str(error), elapsed)
        records.append(record)
        logger.info("%s %s", case.id, record.get("outcome", record.get("error_category")))
        if record.get("error_category") in FATAL_CATEGORIES:
            logger.error("Stopping the run: %s", record["error_message"])
            break

    reported_models = sorted({r["model"] for r in records if r["status"] == "ok"})
    run_info = {
        "kind": "answers",
        "created_utc": run_dir.name.split("_")[0],
        "case_set": options.case_set,
        "cases_file": f"eval/{options.case_set}_cases.jsonl",
        "cases_file_sha256": digest,
        "frozen_check_passed": options.case_set == "frozen",
        "cases_planned": len(cases),
        "cases_run": len(records),
        "retrieval_mode": options.mode,
        "top_k": settings.retrieval.top_k,
        "chunking": settings.chunking.model_dump(),
        "provider": pipeline.service.generator.name,
        "model_configured": settings.generation.model,
        "models_reported": reported_models,
        "reasoning_effort": settings.generation.reasoning_effort or "not sent",
        "embedding_model": settings.embedding.model if needs_embeddings(options.mode) else None,
        "corpus_as_of": settings.corpus.as_of.isoformat(),
        "corpus_fingerprint": pipeline.corpus.fingerprint(),
        "pricing_checked": settings.pricing.checked.isoformat(),
        "git": _git_commit(settings.root),
        "versions": _versions(),
        "platform": platform.platform(),
    }
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return run_dir


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: Strategy
    max_words: int
    overlap_words: int

    @property
    def label(self) -> str:
        return f"{self.strategy}-{self.max_words}-{self.overlap_words}"

    @classmethod
    def parse(cls, text: str) -> ChunkingConfig:
        strategy, max_words, overlap = text.split(":")
        if strategy not in ("section", "window"):
            raise ValueError(f"Unknown chunking strategy: {strategy}")
        return cls(strategy, int(max_words), int(overlap))  # type: ignore[arg-type]


RETRIEVAL_FIELDS = [
    "case_id",
    "category",
    "subtype",
    "chunking",
    "mode",
    "k",
    "rank_sections",
    "retrieved_ids",
    "hit_at_1",
    "hit_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "context_words",
    "search_ms",
    "embedding_tokens",
]


def run_retrieval_experiment(
    settings: Settings,
    case_set: CaseSet,
    modes: list[RetrievalMode],
    chunkings: list[ChunkingConfig],
    k: int,
    embedder: Embedder | None = None,
    results_dir: Path | None = None,
) -> Path:
    cases, digest = _load_set(settings, case_set)
    answerable = [c for c in cases if c.evidence]
    corpus = load_effective_corpus(settings.handbook_dir, settings.corpus.as_of)
    if any(needs_embeddings(m) for m in modes) and embedder is None:
        raise ValueError("Embedding and hybrid modes need an embedder (set OPENAI_API_KEY)")
    # Each question is embedded once, up front and timed, then reused by every configuration,
    # so the search times below measure ranking alone and the API latency is reported apart.
    query_embedder = MemoEmbedder(embedder) if embedder else None
    if query_embedder is not None:
        for case in answerable:
            query_embedder.embed([case.question])

    results_dir = results_dir or settings.root / "eval" / "results"
    run_dir = _run_dir(results_dir, "retrieval", case_set, f"k{k}")
    rows: list[dict] = []
    for config in chunkings:
        chunks = chunk_corpus(corpus, config.max_words, config.overlap_words, config.strategy)
        for mode in modes:
            retriever = build_retriever(
                settings, chunks, embedder, mode=mode, query_embedder=query_embedder
            )
            for case in answerable:
                started = time.perf_counter()
                result = retriever.search(case.question, k)
                elapsed = (time.perf_counter() - started) * 1000
                ranked = [sorted(item.chunk.evidence_keys) for item in result.items]
                score = score_retrieval(case, ranked)
                first = score_retrieval(case, ranked[:1])
                rows.append(
                    {
                        "case_id": case.id,
                        "category": case.category,
                        "subtype": case.subtype,
                        "chunking": config.label,
                        "mode": mode,
                        "k": k,
                        "rank_sections": json.dumps(ranked),
                        "retrieved_ids": json.dumps(result.chunk_ids),
                        "hit_at_1": int(first.hit),
                        "hit_at_k": int(score.hit),
                        "recall_at_k": round(score.recall, 4),
                        "reciprocal_rank": round(score.reciprocal_rank, 4),
                        "context_words": sum(len(i.chunk.text.split()) for i in result.items),
                        "search_ms": round(elapsed, 2),
                        "embedding_tokens": result.embedding_tokens,
                    }
                )

    run_info = {
        "kind": "retrieval",
        "created_utc": run_dir.name.split("_")[0],
        "case_set": case_set,
        "cases_file": f"eval/{case_set}_cases.jsonl",
        "cases_file_sha256": digest,
        "cases_scored": len(answerable),
        "modes": list(modes),
        "chunkings": [c.label for c in chunkings],
        "k": k,
        "keyword_stemming": settings.retrieval.keyword_stemming,
        "hybrid_candidates": settings.retrieval.hybrid_candidates,
        "rrf_k": settings.retrieval.rrf_k,
        "embedding_model": embedder.model if embedder else None,
        "query_embedding_calls": _call_stats(query_embedder),
        "corpus_as_of": settings.corpus.as_of.isoformat(),
        "corpus_fingerprint": corpus.fingerprint(),
        "git": _git_commit(settings.root),
        "versions": _versions(),
        "platform": platform.platform(),
    }
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    with (run_dir / "per_case.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RETRIEVAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return run_dir
