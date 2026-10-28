"""Dense retrieval: cosine similarity over embeddings held in a NumPy array.

With about a hundred chunks, ranking is a single matrix-vector product; the call that
embeds the query takes far longer, so a vector database would add moving parts for nothing.

Embeddings are cached on disk by a hash of the model name and text, so rebuilding the
index after a small edit only pays for the chunks that changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np

from ops_assistant.chunking import Chunk
from ops_assistant.llm.base import Embedder, EmbeddingResult
from ops_assistant.retrieval.base import SearchResult, rank_top

logger = logging.getLogger(__name__)


def _text_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


class EmbeddingCache:
    """A dictionary of text hash -> vector, saved as one .npz file per embedding model."""

    def __init__(self, directory: Path, model: str) -> None:
        self.model = model
        self.path = directory / f"embeddings_{model}.npz"
        self._vectors: dict[str, np.ndarray] = {}
        self.tokens_spent = 0
        if self.path.exists():
            with np.load(self.path) as data:
                keys = json.loads(str(data["keys"]))
                self._vectors = dict(zip(keys, data["vectors"], strict=True))

    def __contains__(self, text: str) -> bool:
        return _text_key(self.model, text) in self._vectors

    def get_or_embed(self, texts: list[str], embedder: Embedder, batch_size: int) -> np.ndarray:
        keys = [_text_key(self.model, t) for t in texts]
        missing = {k: t for k, t in zip(keys, texts, strict=True) if k not in self._vectors}
        if missing:
            logger.info("Embedding %d new texts with %s", len(missing), self.model)
            items = list(missing.items())
            for start in range(0, len(items), batch_size):
                batch = items[start : start + batch_size]
                result = embedder.embed([t for _, t in batch])
                self.tokens_spent += result.input_tokens
                for (key, _), vector in zip(batch, result.vectors, strict=True):
                    self._vectors[key] = np.asarray(vector, dtype=np.float32)
            self.save()
        return np.vstack([self._vectors[k] for k in keys])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self._vectors)
        np.savez(
            self.path,
            keys=np.array(json.dumps(keys)),
            vectors=np.vstack([self._vectors[k] for k in keys]),
        )


def normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class MemoEmbedder:
    """Wraps an embedder for the retrieval experiment: each text is embedded once per run.

    It records the time and retries of every real call, so the report can show the API's
    latency separately from the time spent ranking. Nothing is written to disk.
    """

    def __init__(self, inner: Embedder) -> None:
        self.inner = inner
        self.model = inner.model
        self._vectors: dict[str, np.ndarray] = {}
        self.call_ms: list[float] = []
        self.retries = 0
        self.tokens_spent = 0

    def embed(self, texts: list[str]) -> EmbeddingResult:
        missing = [t for t in dict.fromkeys(texts) if t not in self._vectors]
        tokens = 0
        if missing:
            started = time.perf_counter()
            result = self.inner.embed(missing)
            self.call_ms.append((time.perf_counter() - started) * 1000)
            self.retries += result.retries
            self.tokens_spent += result.input_tokens
            tokens = result.input_tokens
            for text, vector in zip(missing, result.vectors, strict=True):
                self._vectors[text] = np.asarray(vector, dtype=np.float32)
        vectors = np.vstack([self._vectors[t] for t in texts])
        return EmbeddingResult(vectors=vectors, input_tokens=tokens)


class EmbeddingRetriever:
    """Cosine-similarity retriever.

    Chunk vectors come from the on-disk cache. Each question is embedded with
    ``query_embedder`` (the same embedder unless the experiment passes a MemoEmbedder);
    user questions are never written to disk.
    """

    name = "embedding"

    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        cache: EmbeddingCache,
        batch_size: int = 64,
        query_embedder: Embedder | None = None,
    ) -> None:
        self.chunks = chunks
        self.query_embedder = query_embedder or embedder
        matrix = cache.get_or_embed([c.search_text for c in chunks], embedder, batch_size)
        self._matrix = normalise(matrix.astype(np.float32))

    def search(self, query: str, k: int) -> SearchResult:
        started = time.perf_counter()
        result = self.query_embedder.embed([query])
        elapsed_ms = (time.perf_counter() - started) * 1000
        vector = normalise(np.asarray(result.vectors, dtype=np.float32))[0]
        scores = (self._matrix @ vector).tolist()
        return SearchResult(
            items=rank_top(self.chunks, scores, k),
            embedding_tokens=result.input_tokens,
            embedding_ms=elapsed_ms,
            embedding_retries=result.retries,
        )
