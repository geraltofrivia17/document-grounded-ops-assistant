"""Load and validate settings from config/settings.toml plus a few environment overrides."""

from __future__ import annotations

import datetime as dt
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.toml"

RetrievalMode = Literal["keyword", "embedding", "hybrid"]
ProviderName = Literal["openai", "mock"]


class _Frozen(BaseModel):
    # extra="forbid" makes a misspelt key in settings.toml an error, not a silent default.
    model_config = ConfigDict(frozen=True, extra="forbid")


class CorpusSettings(_Frozen):
    handbook_dir: Path
    as_of: dt.date


class ChunkingSettings(_Frozen):
    strategy: Literal["section", "window"]
    max_words: int = Field(gt=10)
    overlap_words: int = Field(ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> ChunkingSettings:
        if self.overlap_words >= self.max_words:
            raise ValueError("overlap_words must be smaller than max_words")
        return self


class RetrievalSettings(_Frozen):
    mode: RetrievalMode
    top_k: int = Field(ge=1, le=20)
    hybrid_candidates: int = Field(ge=1)
    rrf_k: int = Field(ge=1)
    keyword_stemming: bool


class EmbeddingSettings(_Frozen):
    model: str
    cache_dir: Path
    batch_size: int = Field(ge=1, le=2048)
    timeout_seconds: float = Field(gt=0)


class GenerationSettings(_Frozen):
    provider: ProviderName
    model: str
    max_output_tokens: int = Field(ge=50)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0, le=5)
    reasoning_effort: str


class ApiSettings(_Frozen):
    max_question_chars: int = Field(ge=10)
    min_question_chars: int = Field(ge=1)


class ModelPrice(_Frozen):
    input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    output: float = Field(ge=0)


class PricingSettings(_Frozen):
    checked: dt.date
    models: dict[str, ModelPrice]


class Settings(_Frozen):
    corpus: CorpusSettings
    chunking: ChunkingSettings
    retrieval: RetrievalSettings
    embedding: EmbeddingSettings
    generation: GenerationSettings
    api: ApiSettings
    pricing: PricingSettings
    root: Path = PROJECT_ROOT

    @property
    def handbook_dir(self) -> Path:
        return self._resolve(self.corpus.handbook_dir)

    @property
    def embedding_cache_dir(self) -> Path:
        return self._resolve(self.embedding.cache_dir)

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.root / path

    def with_overrides(self, **sections: Mapping[str, object]) -> Settings:
        """Return a copy with some fields replaced.

        Example: ``settings.with_overrides(retrieval={"mode": "keyword"})``.
        """
        data = self.model_dump()
        for section, values in sections.items():
            data[section] = {**data[section], **values}
        return Settings.model_validate(data)


# Environment variable -> (section, field). Kept small on purpose: everything else is in the file.
ENV_OVERRIDES = {
    "OPS_PROVIDER": ("generation", "provider"),
    "OPS_MODEL": ("generation", "model"),
    "OPS_RETRIEVAL_MODE": ("retrieval", "mode"),
    "OPS_TIMEOUT_SECONDS": ("generation", "timeout_seconds"),
}


def load_settings(path: Path | None = None, environ: Mapping[str, str] | None = None) -> Settings:
    """Read settings.toml, apply environment overrides and validate everything."""
    settings_path = path or Path(os.environ.get("OPS_SETTINGS", DEFAULT_SETTINGS_PATH))
    environ = os.environ if environ is None else environ
    with settings_path.open("rb") as handle:
        data = tomllib.load(handle)
    for variable, (section, field) in ENV_OVERRIDES.items():
        if environ.get(variable):
            data.setdefault(section, {})[field] = environ[variable]
    data["root"] = settings_path.resolve().parent.parent
    return Settings.model_validate(data)
