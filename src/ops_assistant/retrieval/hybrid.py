"""Hybrid retrieval by reciprocal rank fusion (RRF).

RRF combines ranks rather than scores: BM25 scores and cosine similarities are on
different scales, and ranks avoid having to calibrate one against the other.
Each chunk scores sum(1 / (rrf_k + rank)) over the lists it appears in.
"""

from __future__ import annotations

from ops_assistant.chunking import Chunk
from ops_assistant.retrieval.base import RetrievedChunk, Retriever, SearchResult


class HybridRetriever:
    name = "hybrid"

    def __init__(
        self, keyword: Retriever, embedding: Retriever, candidates: int = 20, rrf_k: int = 60
    ) -> None:
        self.keyword = keyword
        self.embedding = embedding
        self.candidates = candidates
        self.rrf_k = rrf_k

    def search(self, query: str, k: int) -> SearchResult:
        keyword = self.keyword.search(query, self.candidates)
        embedding = self.embedding.search(query, self.candidates)
        fused: dict[str, float] = {}
        chunks: dict[str, Chunk] = {}
        for result in (keyword, embedding):
            for item in result.items:
                chunk_id = item.chunk.chunk_id
                chunks[chunk_id] = item.chunk
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (self.rrf_k + item.rank)
        order = sorted(fused, key=lambda cid: (-fused[cid], cid))[:k]
        items = [RetrievedChunk(chunks[cid], fused[cid], rank) for rank, cid in enumerate(order, 1)]
        return SearchResult(
            items=items,
            embedding_tokens=embedding.embedding_tokens,
            embedding_ms=embedding.embedding_ms,
            embedding_retries=embedding.embedding_retries,
            details={"keyword": keyword.chunk_ids[:k], "embedding": embedding.chunk_ids[:k]},
        )
