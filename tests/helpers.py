"""Helpers shared by the tests."""

from __future__ import annotations

import json

from ops_assistant.llm.base import GenerationRequest


def reply(
    answer: str = "answer",
    citations: list[str] | None = None,
    outcome: str = "answered",
    conflict_note: str = "",
) -> str:
    return json.dumps(
        {
            "answer": answer,
            "citations": citations or [],
            "conflict_note": conflict_note,
            "outcome": outcome,
        }
    )


def cite_top(request: GenerationRequest) -> str:
    """A well-behaved model: answers and cites the first supplied passage."""
    return reply("From the handbook.", [request.sources[0].source_id])
