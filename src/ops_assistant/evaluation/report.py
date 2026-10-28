"""Turn raw run records into Markdown tables.

Every rate is shown with its count (for example ``27/30 (90%)``), because with ten
cases in a category one case moves the rate by ten points.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ops_assistant.evaluation.cases import CATEGORIES, EvalCase, cases_path, file_hash, load_cases
from ops_assistant.evaluation.review import load_review, write_marks_csv, write_review_workbook
from ops_assistant.evaluation.scoring import (
    AnswerScore,
    RetrievalScore,
    contains_any,
    score_answer,
    score_retrieval,
)

OUTCOME_COLUMNS = ["answered", "insufficient_evidence", "conflicting_evidence", "error"]

Scored = tuple[EvalCase, dict, AnswerScore | None]

ANSWER_RUN_KEYS = [
    ("created_utc", "Run (UTC)"),
    ("case_set", "Case set"),
    ("cases_run", "Cases run"),
    ("cases_file_sha256", "Case file SHA-256"),
    ("provider", "Provider"),
    ("models_reported", "Model reported by the API"),
    ("reasoning_effort", "Reasoning effort"),
    ("retrieval_mode", "Retrieval"),
    ("top_k", "Passages per question"),
    ("chunking", "Chunking"),
    ("embedding_model", "Embedding model"),
    ("corpus_as_of", "Documents in force on"),
    ("corpus_fingerprint", "Corpus fingerprint"),
    ("pricing_checked", "Prices checked"),
    ("git", "Code version"),
    ("versions", "Package versions"),
]

RETRIEVAL_RUN_KEYS = [
    ("created_utc", "Run (UTC)"),
    ("case_set", "Case set"),
    ("cases_scored", "Cases with labelled evidence"),
    ("cases_file_sha256", "Case file SHA-256"),
    ("embedding_model", "Embedding model"),
    ("keyword_stemming", "Keyword stemming"),
    ("hybrid_candidates", "Hybrid candidates per retriever"),
    ("rrf_k", "RRF k"),
    ("corpus_fingerprint", "Corpus fingerprint"),
    ("git", "Code version"),
]


# Formatting helpers


def ratio(count: int, total: int) -> str:
    return f"{count}/{total} ({100 * count / total:.0f}%)" if total else "-"


def table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def percentile(values: list[float], q: float) -> str:
    if not values:
        return "-"
    value = float(np.percentile(values, q))
    return f"{value:.1f}" if value < 10 else f"{value:.0f}"


def _excerpt(text: str, limit: int = 140) -> str:
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _run_details(info: dict, keys: list[tuple[str, str]]) -> str:
    rows = []
    for key, label in keys:
        value = info.get(key)
        if isinstance(value, dict):
            value = ", ".join(f"{k} {v}" for k, v in value.items())
        elif isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        rows.append([label, value])
    return table(["Item", "Value"], rows)


# Loading


def load_run(run_dir: Path, eval_dir: Path | None) -> tuple[dict, dict[str, EvalCase]]:
    """Load run.json and the case file it was run against, refusing if that file changed."""
    info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    # Runs live in eval/results/<run>, so the case files are two levels up by default.
    path = cases_path(eval_dir or run_dir.parent.parent, info["case_set"])
    if file_hash(path) != info["cases_file_sha256"]:
        raise ValueError(
            f"{path.name} has changed since run {run_dir.name}; results would not match"
        )
    return info, {case.id: case for case in load_cases(path)}


def load_records(run_dir: Path) -> list[dict]:
    lines = (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def score_records(records: list[dict], cases: dict[str, EvalCase]) -> list[Scored]:
    scored: list[Scored] = []
    for record in records:
        case = cases[record["id"]]
        if record["status"] != "ok":
            scored.append((case, record, None))
            continue
        sections = {r["id"]: r["sections"] for r in record["retrieved"]}
        scored.append((case, record, score_answer(case, record, sections)))
    return scored


def _retrieval_of(case: EvalCase, record: dict) -> RetrievalScore | None:
    return score_retrieval(case, [r["sections"] for r in record["retrieved"]])


# Answer report sections


def _category_row(category: str, items: list[Scored]) -> list[object]:
    ok = [(c, r, s) for c, r, s in items if s is not None]
    retrieval = [_retrieval_of(c, r) for c, r, _ in ok if c.evidence]
    cites = [s.citation_relevant for _, _, s in ok if s.citation_relevant is not None]
    recall = f"{statistics.mean(r.recall for r in retrieval):.2f}" if retrieval else "-"
    return [
        category,
        len(items),
        ratio(sum(s.passed for _, _, s in ok), len(items)),
        ratio(sum(s.outcome_correct for _, _, s in ok), len(items)),
        ratio(sum(r.hit for r in retrieval), len(retrieval)),
        recall,
        ratio(sum(cites), len(cites)),
        sum(len(r.get("removed_citations", [])) for _, r, _ in ok),
        len(items) - len(ok),
    ]


def category_table(scored: list[Scored]) -> str:
    by_category: dict[str, list[Scored]] = defaultdict(list)
    for item in scored:
        by_category[item[0].category].append(item)
    rows = [_category_row(c, by_category[c]) for c in CATEGORIES if c in by_category]
    headers = [
        "Category",
        "Cases",
        "Passed (auto)",
        "Outcome correct",
        "Evidence retrieved",
        "Evidence recall",
        "Cites relevant section",
        "Citations removed",
        "Errors",
    ]
    return table(headers, rows)


def confusion_table(scored: list[Scored]) -> str:
    counts: Counter[tuple[str, str]] = Counter()
    for case, record, score in scored:
        actual = record["outcome"] if score is not None else "error"
        counts[(case.expected_outcome, actual)] += 1
    rows = [
        [expected, *[counts[(expected, actual)] for actual in OUTCOME_COLUMNS]]
        for expected in OUTCOME_COLUMNS[:3]
        if any(counts[(expected, actual)] for actual in OUTCOME_COLUMNS)
    ]
    return table(["Expected \\ actual", *OUTCOME_COLUMNS], rows)


def performance_table(records: list[dict]) -> str:
    called = [r for r in records if not r["generation_skipped"]]
    measures = [
        ("Retrieval time (ms)", records, "retrieval_ms"),
        ("Generation time (ms)", called, "generation_ms"),
        ("Total time (ms)", records, "total_ms"),
        ("Input tokens", called, "input_tokens"),
        ("Output tokens", called, "output_tokens"),
        ("Reasoning tokens (part of output)", called, "reasoning_tokens"),
    ]
    rows = []
    for label, subset, field in measures:
        values = [r[field] for r in subset]
        rows.append([label, percentile(values, 50), percentile(values, 95)])
    return table(["Measure", "Median", "95th percentile"], rows)


def cost_line(records: list[dict]) -> str:
    costs = [r["cost_usd"] for r in records if r["cost_usd"] is not None]
    retried = [r for r in records if r.get("provider_retries", 0)]
    retry_text = (
        f" Questions that needed a provider retry: {len(retried)} of {len(records)}"
        f" ({sum(r['provider_retries'] for r in retried)} retries)."
    )
    if not costs:
        return "No cost estimate (no priced calls)." + retry_text
    total = sum(costs)
    return (
        f"Estimated cost of this run: ${total:.4f} for {len(costs)} questions "
        f"(${1000 * total / len(costs):.2f} per 1,000 questions at these prices)." + retry_text
    )


def _failure_reason(case: EvalCase, record: dict, score: AnswerScore | None) -> str:
    if score is None:
        return f"error: {record['error_category']} ({record['error_stage']})"
    reasons = []
    if not score.outcome_correct:
        reasons.append(f"outcome {record['outcome']}, expected {case.expected_outcome}")
    text = f"{record['answer']} {record.get('conflict_note', '')}"
    missing = [g[0] for g in case.key_facts + case.computed_facts if not contains_any(text, g)]
    if score.outcome_correct and missing:
        reasons.append("missing " + ", ".join(f'"{m}"' for m in missing))
    if score.forbidden_found:
        reasons.append("said " + ", ".join(f'"{p}"' for p in score.forbidden_found))
    retrieval = _retrieval_of(case, record)
    if retrieval is not None and retrieval.recall < 1:
        found = round(retrieval.recall * len(case.evidence))
        reasons.append(f"retrieved {found} of {len(case.evidence)} evidence sections")
    return "; ".join(reasons) or "-"


def failure_table(scored: list[Scored]) -> str:
    rows = [
        [
            case.id,
            case.category,
            case.subtype,
            _failure_reason(case, record, score),
            _excerpt(record.get("answer", record.get("error_message", ""))),
        ]
        for case, record, score in scored
        if score is None or not score.passed
    ]
    if not rows:
        return "No automatic failures."
    return table(["Case", "Category", "Type", "What went wrong", "Answer (excerpt)"], rows)


def human_review_summary(review_path: Path, scored: list[Scored]) -> str:
    review = load_review(review_path)
    rows = []
    for category in CATEGORIES:
        marks = [review[c.id] for c, _, _ in scored if c.category == category and c.id in review]
        if not marks:
            continue
        reviewed = [m for m in marks if m.correct]
        cited = [m for m in reviewed if m.supported != "na"]
        rows.append(
            [
                category,
                ratio(len(reviewed), len(marks)),
                ratio(sum(m.correct == "yes" for m in reviewed), len(reviewed)),
                ratio(sum(m.correct == "partly" for m in reviewed), len(reviewed)),
                ratio(sum(m.supported == "yes" for m in cited), len(cited)),
                ratio(sum(m.supported == "partly" for m in cited), len(cited)),
            ]
        )
    agreement = [
        score.passed == (review[case.id].correct == "yes")
        for case, _, score in scored
        if score is not None and case.id in review and review[case.id].correct
    ]
    headers = [
        "Category",
        "Reviewed",
        "Correct",
        "Partly correct",
        "Supported by citations",
        "Partly supported",
    ]
    return (
        table(headers, rows)
        + "\n\nAutomatic check agrees with the reviewer on "
        + f"{ratio(sum(agreement), len(agreement))} of reviewed cases."
    )


def answer_summary(
    run_dir: Path, review_path: Path | None = None, eval_dir: Path | None = None
) -> str:
    info, cases = load_run(run_dir, eval_dir)
    scored = score_records(load_records(run_dir), cases)
    ok_records = [record for _, record, score in scored if score is not None]
    parts = [
        f"# Answer evaluation: {run_dir.name}",
        "## Run details",
        _run_details(info, ANSWER_RUN_KEYS),
        "## Results by category",
        "Passed (auto): the expected outcome, every key fact present and no forbidden phrase. "
        "Evidence columns cover cases with labelled evidence. This is an automatic check; "
        "the human review section records whether answers are supported by their citations.",
        category_table(scored),
        "## Outcomes",
        confusion_table(scored),
        "## Time, tokens and cost",
        performance_table(ok_records),
        cost_line(ok_records),
        "## Cases that did not pass the automatic check",
        failure_table(scored),
    ]
    if review_path is not None:
        parts += ["## Human review", human_review_summary(review_path, scored)]
    return "\n\n".join(parts) + "\n"


def write_review_sheet(
    run_dir: Path, eval_dir: Path | None = None, overwrite: bool = False
) -> Path:
    """Create review.xlsx for an answer run. An existing sheet is kept unless overwrite is set."""
    sheet = run_dir / "review.xlsx"
    if overwrite or not sheet.exists():
        _, cases = load_run(run_dir, eval_dir)
        write_review_workbook(sheet, score_records(load_records(run_dir), cases))
    return sheet


def write_answer_report(
    run_dir: Path, review_path: Path | None = None, eval_dir: Path | None = None
) -> Path:
    write_review_sheet(run_dir, eval_dir, overwrite=False)
    if review_path is not None:
        # A plain-text copy of the marks, readable and diffable without Excel.
        write_marks_csv(review_path.parent / "review_marks.csv", load_review(review_path))
    summary = run_dir / "summary.md"
    summary.write_text(answer_summary(run_dir, review_path, eval_dir), encoding="utf-8")
    return summary


# Retrieval report sections


def _mean(items: list[dict], field: str) -> float:
    return statistics.mean(float(item[field]) for item in items)


def configuration_table(groups: dict[tuple[str, str], list[dict]], k: int) -> str:
    rows = []
    for (chunking, mode), items in groups.items():
        times = [float(i["search_ms"]) for i in items]
        rows.append(
            [
                chunking,
                mode,
                len(items),
                ratio(sum(int(i["hit_at_1"]) for i in items), len(items)),
                ratio(sum(int(i["hit_at_k"]) for i in items), len(items)),
                f"{_mean(items, 'recall_at_k'):.2f}",
                f"{_mean(items, 'reciprocal_rank'):.2f}",
                f"{_mean(items, 'context_words'):.0f}",
                percentile(times, 50),
                percentile(times, 95),
            ]
        )
    headers = [
        "Chunking",
        "Mode",
        "Cases",
        "Hit@1",
        f"Hit@{k}",
        f"Recall@{k}",
        "MRR",
        "Context words",
        "Search ms (median)",
        "Search ms (p95)",
    ]
    return table(headers, rows)


def query_embedding_line(stats: dict | None) -> str:
    if not stats:
        return "No embedding API calls in this run."
    return (
        f"Embedding API calls for the questions: {stats['calls']} calls, median "
        f"{stats['median_ms']} ms, 95th percentile {stats['p95_ms']} ms, slowest "
        f"{stats['max_ms']} ms, {stats['retries']} retries. Embedding and hybrid retrieval "
        "add one such call to every question."
    )


def retrieval_category_table(items_by_mode: dict[str, list[dict]], k: int) -> str:
    rows = []
    for mode, items in items_by_mode.items():
        for category in CATEGORIES:
            subset = [i for i in items if i["category"] == category]
            if subset:
                hits = sum(int(i["hit_at_k"]) for i in subset)
                recall = f"{_mean(subset, 'recall_at_k'):.2f}"
                rows.append([mode, category, len(subset), ratio(hits, len(subset)), recall])
    return table(["Mode", "Category", "Cases", f"Hit@{k}", f"Recall@{k}"], rows)


def head_to_head_table(keyword: list[dict], embedding: list[dict]) -> str:
    embedding_hits = {i["case_id"]: int(i["hit_at_k"]) for i in embedding}
    labels = {(1, 1): "both", (1, 0): "keyword only", (0, 1): "embedding only", (0, 0): "neither"}
    buckets: dict[str, list[str]] = {label: [] for label in labels.values()}
    for item in keyword:
        key = (int(item["hit_at_k"]), embedding_hits[item["case_id"]])
        buckets[labels[key]].append(item["case_id"])
    rows = [[label, len(ids), ", ".join(ids) or "-"] for label, ids in buckets.items()]
    return table(["Found by", "Cases", "Case ids"], rows)


def misses_table(items_by_mode: dict[str, list[dict]], cases: dict[str, EvalCase]) -> str:
    rows = []
    for mode, items in items_by_mode.items():
        for item in items:
            if float(item["recall_at_k"]) < 1:
                case = cases[item["case_id"]]
                top = [", ".join(s) for s in json.loads(item["rank_sections"])[:3]]
                question = _excerpt(case.question, 80)
                rows.append([mode, case.id, question, ", ".join(case.evidence), "; ".join(top)])
    if not rows:
        return "None."
    return table(["Mode", "Case", "Question", "Needed", "Top 3 retrieved"], rows)


def retrieval_summary(run_dir: Path, eval_dir: Path | None = None) -> str:
    info, cases = load_run(run_dir, eval_dir)
    with (run_dir / "per_case.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["chunking"], row["mode"])].append(row)

    k = info["k"]
    reference = info["chunkings"][0]
    by_mode = {mode: groups[(reference, mode)] for mode in info["modes"]}
    sections = [
        f"# Retrieval experiment: {run_dir.name}",
        "## Run details",
        _run_details(info, RETRIEVAL_RUN_KEYS),
        "## All configurations",
        "Recall counts how many of a case's required sections appear in the top results. "
        "Context words is the text that would be sent to the model, a proxy for cost. "
        "Search times are ranking only: each question's embedding was fetched once beforehand "
        "and its latency is reported below.",
        configuration_table(groups, k),
        query_embedding_line(info.get("query_embedding_calls")),
        f"## By category ({reference})",
        retrieval_category_table(by_mode, k),
    ]
    if "keyword" in by_mode and "embedding" in by_mode:
        sections += [
            f"## Keyword against embedding ({reference}, hit@{k})",
            head_to_head_table(by_mode["keyword"], by_mode["embedding"]),
        ]
    sections += [f"## Cases with missing evidence ({reference})", misses_table(by_mode, cases)]
    return "\n\n".join(sections) + "\n"


def write_retrieval_report(run_dir: Path, eval_dir: Path | None = None) -> Path:
    summary = run_dir / "summary.md"
    summary.write_text(retrieval_summary(run_dir, eval_dir), encoding="utf-8")
    return summary
