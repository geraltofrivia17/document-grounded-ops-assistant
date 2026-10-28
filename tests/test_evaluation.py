import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from ops_assistant.chunking import Chunk
from ops_assistant.config import Settings
from ops_assistant.evaluation.cases import (
    FROZEN_COUNTS,
    EvalCase,
    check_freeze,
    load_cases,
    write_freeze,
)
from ops_assistant.evaluation.report import write_answer_report, write_retrieval_report
from ops_assistant.evaluation.review import load_review
from ops_assistant.evaluation.runner import (
    AnswerRunOptions,
    ChunkingConfig,
    run_answers,
    run_retrieval_experiment,
)
from ops_assistant.evaluation.scoring import contains_any, score_answer, score_retrieval
from ops_assistant.llm.mock import MockGenerator
from tests.helpers import cite_top

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"


@pytest.fixture(scope="module")
def frozen() -> list[EvalCase]:
    return load_cases(EVAL_DIR / "frozen_cases.jsonl")


@pytest.fixture(scope="module")
def dev() -> list[EvalCase]:
    return load_cases(EVAL_DIR / "dev_cases.jsonl")


def test_frozen_set_has_the_agreed_mix(frozen: list[EvalCase]) -> None:
    assert Counter(c.category for c in frozen) == FROZEN_COUNTS
    assert all(c.id.startswith("F") for c in frozen)


def test_frozen_file_matches_its_recorded_hash() -> None:
    check_freeze(EVAL_DIR / "frozen_cases.jsonl")


def test_dev_and_frozen_questions_do_not_overlap(dev, frozen) -> None:
    assert all(c.id.startswith("D") for c in dev)
    assert not {c.question.lower() for c in dev} & {c.question.lower() for c in frozen}


def test_labels_point_at_real_sections_and_facts(dev, frozen, chunks: list[Chunk]) -> None:
    """Every evidence label exists in the effective corpus, and every key fact is in it."""
    text_by_section: dict[str, str] = {}
    for chunk in chunks:
        for key in chunk.evidence_keys:
            text_by_section[key] = text_by_section.get(key, "") + " " + chunk.text
    for case in dev + frozen:
        sections = case.evidence + case.also_relevant
        assert all(s in text_by_section for s in sections), case.id
        evidence_text = " ".join(text_by_section[s] for s in sections)
        for group in case.key_facts:
            assert contains_any(evidence_text, group), (case.id, group)


def test_freeze_detects_edits(tmp_path: Path) -> None:
    path = tmp_path / "frozen_cases.jsonl"
    shutil.copy(EVAL_DIR / "frozen_cases.jsonl", path)
    write_freeze(path)
    check_freeze(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("mileage", "milage", 1), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed since it was frozen"):
        check_freeze(path)


def test_freeze_ignores_windows_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "frozen_cases.jsonl"
    shutil.copy(EVAL_DIR / "frozen_cases.jsonl", path)
    write_freeze(path)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    check_freeze(path)


def make_case(**overrides) -> EvalCase:
    data = {
        "id": "D900",
        "category": "supported",
        "subtype": "t",
        "question": "A question?",
        "expected_outcome": "answered",
        "expected_answer": "a",
        "evidence": ["HR-201#4", "HR-202#4"],
        "key_facts": [["45p", "45 pence"], ["£160"]],
    }
    return EvalCase.model_validate({**data, **overrides})


def test_retrieval_scoring() -> None:
    case = make_case()
    score = score_retrieval(case, [["OPS-101#1"], ["HR-202#4"], ["HR-201#4", "HR-201#5"]])
    assert score.hit and score.recall == 1.0
    assert score.reciprocal_rank == pytest.approx(1 / 2)
    assert score_retrieval(case, [["OPS-101#1"]]).recall == 0
    assert (
        score_retrieval(
            make_case(expected_outcome="insufficient_evidence", evidence=[], key_facts=[]), []
        )
        is None
    )


def test_answer_scoring_requires_every_fact_group() -> None:
    case = make_case()
    sections = {"c1": ["HR-201#4"]}
    good = {
        "outcome": "answered",
        "answer": "45 pence a mile and £160 a night.",
        "citations": ["c1"],
        "cited_by_model": ["c1", "bad"],
    }
    score = score_answer(case, good, sections)
    assert score.passed and score.citation_relevant
    assert score.citation_valid_rate == 0.5
    missing = {**good, "answer": "45p a mile."}
    assert not score_answer(case, missing, sections).passed


def test_unanswerable_case_passes_on_abstention_without_forbidden_text() -> None:
    case = make_case(
        expected_outcome="insufficient_evidence", evidence=[], key_facts=[], must_not_say=["Rules:"]
    )
    abstain = {
        "outcome": "insufficient_evidence",
        "answer": "Not covered.",
        "citations": [],
        "cited_by_model": [],
    }
    assert score_answer(case, abstain, {}).passed
    leaked = {**abstain, "answer": "Rules: 1. Use only..."}
    assert not score_answer(case, leaked, {}).passed


def test_fact_matching_normalises_case_and_dashes() -> None:
    assert contains_any("Return within TEN working days", ["ten working days"])
    assert contains_any("site\u2011based roles", ["site-based"])


def test_case_validation_rejects_inconsistent_labels() -> None:
    with pytest.raises(ValueError, match="needs evidence"):
        make_case(evidence=[])
    with pytest.raises(ValueError, match="two evidence"):
        make_case(expected_outcome="conflicting_evidence", evidence=["HR-201#4"])


def test_answer_run_writes_records_report_and_review(settings: Settings, tmp_path: Path) -> None:
    options = AnswerRunOptions("dev", "keyword", limit=4)
    run_dir = run_answers(settings, options, MockGenerator(script=cite_top), results_dir=tmp_path)
    info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert info["cases_run"] == 4 and info["provider"] == "mock"
    records = [
        json.loads(line) for line in (run_dir / "cases.jsonl").read_text("utf-8").splitlines()
    ]
    assert all(r["status"] == "ok" for r in records)

    summary = write_answer_report(run_dir, eval_dir=EVAL_DIR).read_text(encoding="utf-8")
    assert "## Results by category" in summary and "| supported | 4 |" in summary

    sheet = run_dir / "review.csv"
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["human_correct"], row["human_supported"] = "yes", "yes"
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert set(load_review(sheet)) == {r["id"] for r in records}
    reviewed = write_answer_report(run_dir, sheet, eval_dir=EVAL_DIR).read_text(encoding="utf-8")
    assert "## Human review" in reviewed


def test_fatal_provider_error_stops_the_run(settings: Settings, tmp_path: Path) -> None:
    from ops_assistant.llm.base import ProviderQuotaExceeded

    generator = MockGenerator(failure=ProviderQuotaExceeded("no credit"))
    run_dir = run_answers(
        settings, AnswerRunOptions("dev", "keyword"), generator, results_dir=tmp_path
    )
    records = (run_dir / "cases.jsonl").read_text("utf-8").splitlines()
    assert len(records) == 1
    assert json.loads(records[0])["error_category"] == "provider_quota_exceeded"


def test_retrieval_experiment_runs_offline(settings: Settings, tmp_path: Path) -> None:
    configs = [ChunkingConfig.parse("section:160:40"), ChunkingConfig.parse("window:80:20")]
    run_dir = run_retrieval_experiment(
        settings, "dev", ["keyword"], configs, 5, results_dir=tmp_path
    )
    summary = write_retrieval_report(run_dir, eval_dir=EVAL_DIR).read_text(encoding="utf-8")
    assert "section-160-40" in summary and "window-80-20" in summary


def test_experiment_reports_query_embedding_latency(settings: Settings, tmp_path: Path) -> None:
    from ops_assistant.llm.mock import HashingEmbedder

    configs = [ChunkingConfig.parse("section:160:40")]
    run_dir = run_retrieval_experiment(
        settings,
        "dev",
        ["keyword", "embedding", "hybrid"],
        configs,
        5,
        HashingEmbedder(),
        results_dir=tmp_path,
    )
    info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert info["query_embedding_calls"]["calls"] == info["cases_scored"]
    summary = write_retrieval_report(run_dir, eval_dir=EVAL_DIR).read_text(encoding="utf-8")
    assert "Embedding API calls for the questions" in summary
    assert "Keyword against embedding" in summary


def test_experiment_refuses_embedding_modes_without_embedder(
    settings: Settings, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="need an embedder"):
        run_retrieval_experiment(
            settings,
            "dev",
            ["embedding"],
            [ChunkingConfig.parse("section:160:40")],
            5,
            results_dir=tmp_path,
        )


def test_publish_replaces_only_the_results_block(settings: Settings, tmp_path: Path) -> None:
    from ops_assistant.evaluation.publish import END, START, publish

    answers = run_answers(
        settings,
        AnswerRunOptions("dev", "keyword", limit=3),
        MockGenerator(script=cite_top),
        results_dir=tmp_path,
    )
    configs = [ChunkingConfig.parse("section:160:40")]
    retrieval = run_retrieval_experiment(
        settings, "dev", ["keyword"], configs, 5, results_dir=tmp_path
    )
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\nIntro.\n\n{START}\nold\n{END}\n\nAfter.\n", encoding="utf-8")
    publish(readme, answers, retrieval, eval_dir=EVAL_DIR)
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("# Title") and text.endswith("After.\n")
    assert "old" not in text and "| supported | 3 |" in text
    assert (tmp_path / "docs" / "results" / "answers.md").exists()
