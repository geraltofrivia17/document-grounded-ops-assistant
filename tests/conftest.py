"""Shared fixtures. No test calls a network service: generation uses MockGenerator and
embeddings use HashingEmbedder."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ops_assistant.chunking import Chunk
from ops_assistant.config import Settings, load_settings
from ops_assistant.llm.mock import HashingEmbedder, MockGenerator
from ops_assistant.service import Pipeline, build_pipeline, load_chunks
from tests.helpers import cite_top


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guarantees the suite never reaches the real provider, even on a machine with a key set.
    for variable in (
        "OPENAI_API_KEY",
        "OPS_PROVIDER",
        "OPS_MODEL",
        "OPS_RETRIEVAL_MODE",
        "OPS_TIMEOUT_SECONDS",
        "OPS_SETTINGS",
    ):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    base = load_settings()
    # Embedding caches go to a temporary folder so tests never touch data/index.
    return base.with_overrides(
        retrieval={"mode": "keyword"}, embedding={"cache_dir": str(tmp_path / "index")}
    )


@pytest.fixture
def chunks(settings: Settings) -> list[Chunk]:
    return load_chunks(settings)[1]


@pytest.fixture
def make_pipeline(settings: Settings) -> Callable[..., Pipeline]:
    def factory(generator: MockGenerator | None = None, mode: str = "keyword") -> Pipeline:
        generator = generator or MockGenerator(script=cite_top)
        embedder = HashingEmbedder() if mode != "keyword" else None
        return build_pipeline(settings, generator, embedder, mode=mode)

    return factory
