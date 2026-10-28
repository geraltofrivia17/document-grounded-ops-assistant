"""Automatic scoring for one evaluation case.

Retrieval and answers are scored separately, so a plausible answer cannot hide a
retrieval miss, and a good retrieval cannot hide a bad answer.

Automatic answer checks are a proxy: they look for the key facts and the expected
outcome. Whether the cited passages actually support what the answer says is judged
by a person in the review sheet (see review.py), because string matching cannot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ops_assistant.evaluation.cases import EvalCase

# Unicode hyphens and dashes (U+2010 to U+2015) are compared as "-".
DASHES = re.compile("[\u2010-\u2015]")


def normalise_text(text: str) -> str:
    text = DASHES.sub("-", text.lower().replace("\u2019", "'"))
    return " ".join(text.split())


def contains_any(text: str, alternatives: list[str]) -> bool:
    normalised = normalise_text(text)
    return any(normalise_text(option) in normalised for option in alternatives)


@dataclass(frozen=True)
class RetrievalScore:
    hit: bool
    recall: float
    reciprocal_rank: float


def score_retrieval(case: EvalCase, ranked_sections: list[list[str]]) -> RetrievalScore | None:
    """ranked_sections holds, for each retrieved chunk in rank order, the sections it covers."""
    if not case.evidence:
        return None
    required = set(case.evidence)
    found: set[str] = set()
    first_rank = 0
    for rank, sections in enumerate(ranked_sections, start=1):
        matched = required & set(sections)
        if matched and not first_rank:
            first_rank = rank
        found |= matched
    return RetrievalScore(
        hit=bool(found),
        recall=len(found) / len(required),
        reciprocal_rank=1 / first_rank if first_rank else 0.0,
    )


@dataclass(frozen=True)
class AnswerScore:
    outcome_correct: bool
    facts_correct: bool | None
    forbidden_found: list[str]
    citation_valid_rate: float | None
    citation_relevant: bool | None
    # Answerable: right outcome and every key fact present. Unanswerable: right outcome
    # and none of the forbidden phrases.
    passed: bool


def score_answer(
    case: EvalCase, record: dict, sections_by_chunk: dict[str, list[str]]
) -> AnswerScore:
    """Score a successful run record. Failed requests are counted separately as errors."""
    outcome_correct = record["outcome"] == case.expected_outcome
    text = f"{record['answer']} {record.get('conflict_note', '')}"
    forbidden = [phrase for phrase in case.must_not_say if contains_any(text, [phrase])]

    facts_correct = None
    if case.answerable:
        groups = case.key_facts + case.computed_facts
        facts_correct = (
            outcome_correct and all(contains_any(text, g) for g in groups) and not forbidden
        )

    cited = record.get("cited_by_model", [])
    valid = record.get("citations", [])
    citation_valid_rate = len(valid) / len(cited) if cited else None

    citation_relevant = None
    if case.answerable and record["outcome"] != "insufficient_evidence":
        relevant = case.relevant_sections
        citation_relevant = any(
            relevant & set(sections_by_chunk.get(chunk_id, [])) for chunk_id in valid
        )
    passed = bool(facts_correct) if case.answerable else outcome_correct and not forbidden
    return AnswerScore(
        outcome_correct=outcome_correct,
        facts_correct=facts_correct,
        forbidden_found=forbidden,
        citation_valid_rate=citation_valid_rate,
        citation_relevant=citation_relevant,
        passed=passed,
    )
