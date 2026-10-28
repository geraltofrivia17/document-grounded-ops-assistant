"""Write the headline results into README.md and copy the full tables into docs/results.

The README block between the results markers is generated, never edited by hand, so
every number in it can be traced to a saved run.
"""

from __future__ import annotations

import csv
import json
import shutil
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
from ops_assistant.evaluation.review import load_review

START = "<!-- results:start -->"
END = "<!-- results:end -->"


def _answer_rows(answer_run: Path, review_path: Path | None, eval_dir: Path | None) -> list[list]:
    _, cases = load_run(answer_run, eval_dir)
    scored = score_records(load_records(answer_run), cases)
    review = load_review(review_path) if review_path else {}
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
                ratio(sum(int(i["hit_at_k"]) for i in items), len(items)),
                f"{statistics.mean(float(i['recall_at_k']) for i in items):.2f}",
                f"{statistics.mean(float(i['reciprocal_rank']) for i in items):.2f}",
                percentile([float(i["search_ms"]) for i in items], 50),
            ]
        )
    return table_rows, info


def results_block(
    answer_run: Path,
    retrieval_run: Path,
    review_path: Path | None = None,
    eval_dir: Path | None = None,
) -> str:
    info = json.loads((answer_run / "run.json").read_text(encoding="utf-8"))
    records = [r for r in load_records(answer_run) if r["status"] == "ok"]
    retrieval_rows, retrieval_info = _retrieval_rows(retrieval_run)
    k = retrieval_info["k"]
    costs = [r["cost_usd"] for r in records if r["cost_usd"] is not None]
    per_thousand = f"${1000 * sum(costs) / len(costs):.2f}" if costs else "unknown"
    totals = [r["total_ms"] for r in records]
    model = ", ".join(info["models_reported"]) or info["model_configured"]
    commit = str(info["git"]["commit"])[:7]
    reviewed = "with human review" if review_path else "automatic checks only"
    return "\n\n".join(
        [
            START,
            f"Frozen evaluation set, {info['cases_run']} cases, run {info['created_utc']} with "
            f"`{model}` and {info['retrieval_mode']} retrieval ({reviewed}; case file "
            f"`{info['cases_file_sha256'][:12]}`, commit `{commit}`). Full tables: "
            "[answers](docs/results/answers.md), [retrieval](docs/results/retrieval.md).",
            table(
                [
                    "Category",
                    "Cases",
                    "Passed automatic check",
                    "Correct (human)",
                    "Supported by citations (human)",
                ],
                _answer_rows(answer_run, review_path, eval_dir),
            ),
            f"Retrieval on the {retrieval_info['cases_scored']} answerable frozen questions "
            f"(top {k}, {retrieval_info['chunkings'][0]} chunks):",
            table(["Mode", f"Hit@{k}", f"Recall@{k}", "MRR", "Search ms (median)"], retrieval_rows),
            f"Response time: median {percentile(totals, 50)} ms, 95th percentile "
            f"{percentile(totals, 95)} ms. Estimated cost: {per_thousand} per 1,000 questions "
            f"at prices checked {info['pricing_checked']}.",
            END,
        ]
    )


def publish(
    readme: Path,
    answer_run: Path,
    retrieval_run: Path,
    review_path: Path | None = None,
    eval_dir: Path | None = None,
) -> None:
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError(f"{readme.name} has no results markers")
    block = results_block(answer_run, retrieval_run, review_path, eval_dir)
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(before + block + after, encoding="utf-8")

    results_dir = readme.parent / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    answers = answer_summary(answer_run, review_path, eval_dir)
    (results_dir / "answers.md").write_text(answers, encoding="utf-8")
    (results_dir / "retrieval.md").write_text(retrieval_summary(retrieval_run, eval_dir), "utf-8")
    if review_path:
        shutil.copy(review_path, results_dir / "review.csv")
