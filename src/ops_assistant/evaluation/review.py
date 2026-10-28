"""Human review sheet for grounding and correctness.

Citation validation only proves that an answer points at real passages that were
supplied. Whether those passages support what the answer says needs a reader, so each
answer run writes ``review.csv``. The reviewer fills in two columns per case:

``human_correct``   yes / partly / no: does the answer match the reference answer?
``human_supported`` yes / partly / no / na: is every claim backed by the cited text?
                    Use na when the answer cites nothing (for example an abstention).

The file is written with a byte-order mark so Excel shows £ signs correctly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REVIEW_FIELDS = [
    "case_id",
    "category",
    "subtype",
    "question",
    "expected_answer",
    "scoring_guidance",
    "outcome",
    "answer",
    "conflict_note",
    "cited_passages",
    "auto_passed",
    "human_correct",
    "human_supported",
    "human_notes",
]
CORRECT_VALUES = {"", "yes", "partly", "no"}
SUPPORTED_VALUES = {"", "yes", "partly", "no", "na"}


@dataclass(frozen=True)
class ReviewMark:
    correct: str
    supported: str
    notes: str


def write_review_sheet(path: Path, scored: list) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for case, record, score in scored:
            passages = "\n\n".join(
                f"[{chunk_id}] {text}" for chunk_id, text in record.get("cited_text", {}).items()
            )
            writer.writerow(
                {
                    "case_id": case.id,
                    "category": case.category,
                    "subtype": case.subtype,
                    "question": case.question,
                    "expected_answer": case.expected_answer,
                    "scoring_guidance": case.scoring,
                    "outcome": record.get("outcome", f"error: {record.get('error_category')}"),
                    "answer": record.get("answer", record.get("error_message", "")),
                    "conflict_note": record.get("conflict_note", ""),
                    "cited_passages": passages,
                    "auto_passed": "" if score is None else ("yes" if score.passed else "no"),
                    "human_correct": "",
                    "human_supported": "",
                    "human_notes": "",
                }
            )


def load_review(path: Path) -> dict[str, ReviewMark]:
    marks: dict[str, ReviewMark] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            correct = row["human_correct"].strip().lower()
            supported = row["human_supported"].strip().lower()
            if correct not in CORRECT_VALUES or supported not in SUPPORTED_VALUES:
                raise ValueError(
                    f"{row['case_id']}: human_correct must be yes/partly/no and "
                    "human_supported yes/partly/no/na"
                )
            marks[row["case_id"]] = ReviewMark(correct, supported, row["human_notes"].strip())
    return marks
