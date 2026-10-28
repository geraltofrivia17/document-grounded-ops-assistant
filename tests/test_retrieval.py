from pathlib import Path

import pytest

from ops_assistant.chunking import Chunk
from ops_assistant.llm.mock import HashingEmbedder
from ops_assistant.retrieval import (
    BM25Retriever,
    EmbeddingCache,
    EmbeddingRetriever,
    HybridRetriever,
    MemoEmbedder,
    RetrievedChunk,
    SearchResult,
)
from ops_assistant.retrieval.keyword import Tokenizer


def test_bm25_finds_the_mileage_section(chunks: list[Chunk]) -> None:
    result = BM25Retriever(chunks).search("What mileage rate applies to my own car?", 5)
    assert result.chunk_ids[0] == "HR-201:v4.0:s4:c1"
    assert [item.rank for item in result.items] == [1, 2, 3, 4, 5]


def test_bm25_returns_nothing_when_no_term_matches(chunks: list[Chunk]) -> None:
    assert BM25Retriever(chunks).search("zebra xylophone quokka", 5).items == []


def test_tokenizer_keeps_negations_and_currency() -> None:
    tokens = Tokenizer(stemming=False)("Can it NOT be paid without £45?")
    assert tokens == ["not", "paid", "without", "£45"]


def test_stemming_matches_word_forms() -> None:
    stem = Tokenizer(stemming=True)
    assert stem("returned claims") == stem("return claim")


def test_results_are_deterministic(chunks: list[Chunk]) -> None:
    retriever = BM25Retriever(chunks)
    assert retriever.search("laptop", 10).chunk_ids == retriever.search("laptop", 10).chunk_ids


def test_embedding_retriever_ranks_and_caches(chunks: list[Chunk], tmp_path: Path) -> None:
    embedder = HashingEmbedder()
    cache = EmbeddingCache(tmp_path, embedder.model)
    retriever = EmbeddingRetriever(chunks, embedder, cache, batch_size=50)
    assert cache.path.exists()
    first_calls = embedder.calls
    assert first_calls == 2  # 94 chunks in batches of 50

    result = retriever.search("mileage rate own car business journeys", 3)
    assert len(result.items) == 3
    assert result.embedding_tokens > 0

    # A second index over the same text is served from the cache file.
    reloaded = EmbeddingCache(tmp_path, embedder.model)
    EmbeddingRetriever(chunks, embedder, reloaded, batch_size=50)
    assert embedder.calls == first_calls + 1  # only the query above
    assert reloaded.tokens_spent == 0


def test_cache_is_keyed_by_model(tmp_path: Path) -> None:
    EmbeddingCache(tmp_path, "model-a").get_or_embed(["text"], HashingEmbedder(), 10)
    other = EmbeddingCache(tmp_path, "model-b")
    assert "text" not in other


class FixedRetriever:
    def __init__(self, name: str, chunks: list[Chunk]) -> None:
        self.name = name
        self._chunks = chunks

    def search(self, query: str, k: int) -> SearchResult:
        items = [RetrievedChunk(c, 1.0, rank) for rank, c in enumerate(self._chunks[:k], 1)]
        return SearchResult(items=items, embedding_tokens=7 if self.name == "embedding" else 0)


def test_hybrid_uses_reciprocal_rank_fusion(chunks: list[Chunk]) -> None:
    a, b, c = chunks[:3]
    keyword = FixedRetriever("keyword", [a, b])
    embedding = FixedRetriever("embedding", [b, c])
    result = HybridRetriever(keyword, embedding, candidates=5, rrf_k=60).search("q", 3)
    # b is ranked by both lists, so it comes first: 1/62 + 1/61.
    assert result.chunk_ids[0] == b.chunk_id
    assert result.items[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert set(result.chunk_ids) == {a.chunk_id, b.chunk_id, c.chunk_id}
    assert result.embedding_tokens == 7
    assert result.details["keyword"] == [a.chunk_id, b.chunk_id]


def test_memo_embedder_calls_once_per_text_and_times_calls() -> None:
    inner = HashingEmbedder()
    memo = MemoEmbedder(inner)
    first = memo.embed(["a question"])
    again = memo.embed(["a question"])
    assert inner.calls == 1
    assert len(memo.call_ms) == 1
    assert first.input_tokens > 0 and again.input_tokens == 0
    assert (first.vectors == again.vectors).all()


def test_embedding_search_uses_the_query_embedder(chunks: list[Chunk], tmp_path: Path) -> None:
    corpus_embedder = HashingEmbedder()
    query_embedder = MemoEmbedder(HashingEmbedder())
    cache = EmbeddingCache(tmp_path, corpus_embedder.model)
    retriever = EmbeddingRetriever(chunks, corpus_embedder, cache, query_embedder=query_embedder)
    calls_after_index = corpus_embedder.calls
    retriever.search("mileage", 3)
    assert corpus_embedder.calls == calls_after_index
    assert len(query_embedder.call_ms) == 1
