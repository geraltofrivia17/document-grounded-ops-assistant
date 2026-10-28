"""Evaluation cases, loading, and the freeze check for the held-out set.

The frozen set is hashed once, before any live run. ``eval answers --set frozen``
refuses to run if the file no longer matches the recorded hash, so the held-out
questions cannot be quietly edited after seeing results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ops_assistant.answer import Outcome

Category = Literal["supported", "unsupported", "multi_document", "adversarial"]
CaseSet = Literal["dev", "frozen"]

CATEGORIES: tuple[Category, ...] = ("supported", "unsupported", "multi_document", "adversarial")
FROZEN_COUNTS = {"supported": 30, "unsupported": 10, "multi_document": 10, "adversarial": 10}


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[DF]\d{3}$")
    category: Category
    subtype: str
    question: str = Field(min_length=3)
    expected_outcome: Outcome
    expected_answer: str
    # Sections (DOC-ID#section) needed to answer. Retrieval recall is measured against these.
    evidence: list[str] = Field(default_factory=list)
    # Sections that also support the answer; citing them is not counted as irrelevant.
    also_relevant: list[str] = Field(default_factory=list)
    # Each inner list is a set of acceptable spellings; every group must appear in the answer.
    key_facts: list[list[str]] = Field(default_factory=list)
    # Like key_facts, but derived by arithmetic, so they need not appear in the sources.
    computed_facts: list[list[str]] = Field(default_factory=list)
    must_not_say: list[str] = Field(default_factory=list)
    scoring: str = ""

    @property
    def answerable(self) -> bool:
        return self.expected_outcome != "insufficient_evidence"

    @property
    def relevant_sections(self) -> set[str]:
        return set(self.evidence) | set(self.also_relevant)

    @model_validator(mode="after")
    def _labels_are_consistent(self) -> EvalCase:
        if self.answerable and not self.evidence:
            raise ValueError(f"{self.id}: an answerable case needs evidence")
        if self.answerable and not (self.key_facts or self.computed_facts):
            raise ValueError(f"{self.id}: an answerable case needs key facts")
        if self.expected_outcome == "conflicting_evidence" and len(self.evidence) < 2:
            raise ValueError(f"{self.id}: a conflict case needs at least two evidence sections")
        return self


def cases_path(eval_dir: Path, case_set: CaseSet) -> Path:
    return eval_dir / f"{case_set}_cases.jsonl"


def load_cases(path: Path) -> list[EvalCase]:
    cases = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    cases.append(EvalCase.model_validate(json.loads(line)))
                except ValueError as error:
                    raise ValueError(f"{path.name} line {number}: {error}") from error
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: duplicate case ids")
    return cases


def file_hash(path: Path) -> str:
    # Line endings are normalised so a Windows checkout with CRLF gives the same hash.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def hash_path(cases_file: Path) -> Path:
    return cases_file.with_suffix(".sha256")


def write_freeze(cases_file: Path) -> str:
    digest = file_hash(cases_file)
    hash_path(cases_file).write_text(f"{digest}  {cases_file.name}\n", encoding="utf-8")
    return digest


def check_freeze(cases_file: Path) -> str:
    """Return the hash if the file matches its recorded freeze, otherwise raise."""
    recorded_file = hash_path(cases_file)
    if not recorded_file.exists():
        raise ValueError(f"{cases_file.name} has not been frozen")
    recorded = recorded_file.read_text(encoding="utf-8").split()[0]
    actual = file_hash(cases_file)
    if actual != recorded:
        raise ValueError(
            f"{cases_file.name} has changed since it was frozen "
            f"(recorded {recorded[:12]}, now {actual[:12]}). Frozen cases must not be edited."
        )
    return actual
