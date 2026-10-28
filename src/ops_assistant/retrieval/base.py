"""Shared types for the retrievers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ops_assistant.chunking import Chunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    rank: int


@dataclass(frozen=True)
class SearchResult:
    """Ranked chunks plus what the search cost, so the API can report it per request."""

    items: list[RetrievedChunk]
    embedding_tokens: int = 0
    embedding_ms: float = 0.0
    embedding_retries: int = 0
    details: dict[str, list[str]] = field(default_factory=dict)

    @property
    def chunk_ids(self) -> list[str]:
        return [item.chunk.chunk_id for item in self.items]


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int) -> SearchResult:
        """Return up to k chunks, best first. May return fewer, or none."""
        ...


def rank_top(chunks: list[Chunk], scores: list[float], k: int) -> list[RetrievedChunk]:
    """Sort by score (ties broken by corpus order, so results are deterministic) and keep k."""
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))[:k]
    return [RetrievedChunk(chunks[i], float(scores[i]), rank) for rank, i in enumerate(order, 1)]
