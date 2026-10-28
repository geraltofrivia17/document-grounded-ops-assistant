"""Write the headline results into README.md and copy the full tables into docs/results.

The README block between the results markers is generated, never edited by hand, so
every number in it can be traced to a saved run.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path

from ops_assistant.evaluation.cases import CATEGORIES
from ops_assistant.evaluation.report import (
    answer_summary,
    load_records,
    load_run,
    percentile,
    ratio,
    retrieval_summary,
    score_records,
    table,
)
from ops_assistant.evaluation.review import ReviewMark, load_review, write_marks_csv

START = "<!-- results:start -->"
END = "<!-- results:end -->"


def _run_date(stamp: str) -> str:
    """'20261028T125111Z' -> '28 October 2026'."""
    day = dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    return f"{day.day} {day:%B %Y}"


def _answer_rows(
    answer_run: Path, review: dict[str, ReviewMark], eval_dir: Path | None
) -> list[list]:
    _, cases = load_run(answer_run, eval_dir)
    scored = score_records(load_records(answer_run), cases)
    rows = []
    for category in CATEGORIES:
        items = [item for item in scored if item[0].category == category]
        if not items:
            continue
        passed = sum(1 for _, _, s in items if s is not None and s.passed)
        marks = [review[c.id] for c, _, _ in items if c.id in review and review[c.id].correct]
        cited = [m for m in marks if m.supported != "na"]
        rows.append(
            [
                category.replace("_", " "),
                len(items),
                ratio(passed, len(items)),
                ratio(sum(m.correct == "yes" for m in marks), len(marks)) if review else "-",
                ratio(sum(m.supported == "yes" for m in cited), len(cited)) if review else "-",
            ]
        )
    return rows


def _mode_row(answer_run: Path, eval_dir: Path | None) -> list[object]:
    """One retrieval mode's answer run: automatic passes, false refusals, time and cost."""
    info, cases = load_run(answer_run, eval_dir)
    scored = score_records(load_records(answer_run), cases)
    ok = [(c, r, s) for c, r, s in scored if s is not None]
    answerable = [(c, r) for c, r, _ in ok if c.answerable]
    declined = sum(1 for _, r in answerable if r["outcome"] == "insufficient_evidence")
    costs = [r["cost_usd"] for _, r, _ in ok if r["cost_usd"] is not None]
    return [
        info["retrieval_mode"],
        ratio(sum(s.passed for _, _, s in ok), len(scored)),
        f"{declined} of {len(answerable)}",
        percentile([r["total_ms"] for _, r, _ in ok], 50),
        f"${1000 * sum(costs) / len(costs):.2f}" if costs else "unknown",
    ]


def _retrieval_rows(retrieval_run: Path) -> tuple[list[list], dict]:
    info = json.loads((retrieval_run / "run.json").read_text(encoding="utf-8"))
    with (retrieval_run / "per_case.csv").open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["chunking"] == info["chunkings"][0]]
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)
    table_rows = []
    for mode, items in by_mode.items():
        table_rows.append(
            [
                mode,
                ratio(sum(int(i["hit_at_1"]) for i in items), len(items)),
                ratio(sum(int(i["hit_at_k"]) for i in items), len(items)),
                f"{statistics.mean(float(i['recall_at_k']) for i in items):.2f}",
                f"{statistics.mean(float(i['reciprocal_rank']) for i in items):.2f}",
            ]
        )
    return table_rows, info


def _review_findings(review: dict[str, ReviewMark]) -> str:
    flagged = []
    for case_id, mark in review.items():
        issues = [f"correct: {mark.correct}"] if mark.correct in ("partly", "no") else []
        if mark.supported in ("partly", "no"):
            issues.append(f"supported: {mark.supported}")
        if issues:
            flagged.append(f"{case_id} ({', '.join(issues)})")
    if not flagged:
        return "No answer was marked partly or no on review."
    return (
        f"Marked partly or no on review: {'; '.join(flagged)}. The reviewer's note on every "
        "case is in [docs/results/review_marks.csv](docs/results/review_marks.csv)."
    )


def results_block(
    answer_run: Path,
    retrieval_run: Path,
    review_path: Path | None = None,
    eval_dir: Path | None = None,
    compare_runs: tuple[Path, ...] = (),
) -> str:
    info = json.loads((answer_run / "run.json").read_text(encoding="utf-8"))
    review = load_review(review_path) if review_path else {}
    records = [r for r in load_records(answer_run) if r["status"] == "ok"]
    retrieval_rows, retrieval_info = _retrieval_rows(retrieval_run)
    k = retrieval_info["k"]
    totals = [r["total_ms"] for r in records]
    model = ", ".join(info["models_reported"]) or info["model_configured"]
    commit = str(info["git"]["commit"])[:7]
    reviewed = "answers reviewed by hand" if review else "automatic checks only"
    parts = [
        START,
        f"Frozen evaluation set: {info['cases_run']} questions, run on "
        f"{_run_date(info['created_utc'])} with `{model}` and {info['retrieval_mode']} "
        f"retrieval ({reviewed}; case file `{info['cases_file_sha256'][:12]}`, commit "
        f"`{commit}`). Full tables: [answers](docs/results/answers.md), "
        "[retrieval](docs/results/retrieval.md).",
        table(
            [
                "Category",
                "Questions",
                "Passed automatic check",
                "Correct (human review)",
                "Supported by its citations (human review)",
            ],
            _answer_rows(answer_run, review, eval_dir),
        ),
    ]
    if review:
        parts.append(
            "Support is judged only for answers that cite passages; a refusal that cites "
            "nothing is not counted. " + _review_findings(review)
        )
    parts += [
        f"Retrieval on the {retrieval_info['cases_scored']} answerable frozen questions "
        f"(top {k}, {retrieval_info['chunkings'][0]} chunks):",
        table(["Mode", "Hit@1", f"Hit@{k}", f"Recall@{k}", "MRR"], retrieval_rows),
    ]
    calls = retrieval_info.get("query_embedding_calls")
    if calls:
        parts.append(
            f"Embedding and hybrid retrieval add one embedding call per question: median "
            f"{calls['median_ms']} ms, 95th percentile {calls['p95_ms']} ms "
            f"({calls['calls']} calls)."
        )
    if compare_runs:
        parts += [
            "The same 60 questions answered with each retrieval mode (decided before the run: "
            f"{info['retrieval_mode']} is the reported configuration, the others are comparisons):",
            table(
                [
                    "Retrieval",
                    "Passed automatic check",
                    "Answerable questions declined",
                    "Median response ms",
                    "Cost per 1,000 questions",
                ],
                [_mode_row(run, eval_dir) for run in (answer_run, *compare_runs)],
            ),
        ]
    parts += [
        f"Response time ({info['retrieval_mode']}): median {percentile(totals, 50)} ms, 95th "
        f"percentile {percentile(totals, 95)} ms. Costs are estimates from token counts at prices "
        f"checked on {info['pricing_checked']}.",
        END,
    ]
    return "\n\n".join(parts)


def publish(
    readme: Path,
    answer_run: Path,
    retrieval_run: Path,
    review_path: Path | None = None,
    eval_dir: Path | None = None,
    compare_runs: tuple[Path, ...] = (),
) -> None:
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError(f"{readme.name} has no results markers")
    block = results_block(answer_run, retrieval_run, review_path, eval_dir, compare_runs)
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(before + block + after, encoding="utf-8")

    results_dir = readme.parent / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    answers = answer_summary(answer_run, review_path, eval_dir)
    (results_dir / "answers.md").write_text(answers, encoding="utf-8")
    (results_dir / "retrieval.md").write_text(retrieval_summary(retrieval_run, eval_dir), "utf-8")
    if review_path:
        write_marks_csv(results_dir / "review_marks.csv", load_review(review_path))
