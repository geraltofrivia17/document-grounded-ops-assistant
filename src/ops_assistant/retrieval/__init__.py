"""Retriever construction from settings."""

from __future__ import annotations

from ops_assistant.chunking import Chunk
from ops_assistant.config import RetrievalMode, Settings
from ops_assistant.llm.base import Embedder
from ops_assistant.retrieval.base import RetrievedChunk, Retriever, SearchResult
from ops_assistant.retrieval.embedding import EmbeddingCache, EmbeddingRetriever, MemoEmbedder
from ops_assistant.retrieval.hybrid import HybridRetriever
from ops_assistant.retrieval.keyword import BM25Retriever

__all__ = [
    "BM25Retriever",
    "EmbeddingCache",
    "EmbeddingRetriever",
    "HybridRetriever",
    "MemoEmbedder",
    "RetrievedChunk",
    "Retriever",
    "SearchResult",
    "build_retriever",
]


def needs_embeddings(mode: RetrievalMode) -> bool:
    return mode in ("embedding", "hybrid")


def build_retriever(
    settings: Settings,
    chunks: list[Chunk],
    embedder: Embedder | None = None,
    mode: RetrievalMode | None = None,
    query_embedder: Embedder | None = None,
) -> Retriever:
    mode = mode or settings.retrieval.mode
    keyword = BM25Retriever(chunks, stemming=settings.retrieval.keyword_stemming)
    if mode == "keyword":
        return keyword
    if embedder is None:
        raise ValueError(f"Retrieval mode '{mode}' needs an embedder")
    cache = EmbeddingCache(settings.embedding_cache_dir, embedder.model)
    embedding = EmbeddingRetriever(
        chunks, embedder, cache, settings.embedding.batch_size, query_embedder=query_embedder
    )
    if mode == "embedding":
        return embedding
    return HybridRetriever(
        keyword, embedding, settings.retrieval.hybrid_candidates, settings.retrieval.rrf_k
    )
