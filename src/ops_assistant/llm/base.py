"""Provider-neutral interfaces for text generation and embeddings.

The rest of the code depends only on these types, so adding a second provider means
writing one new module, not changing the answering pipeline.

Every provider failure is raised as a ProviderError subclass with a stable
``category``. The API returns that category to the caller, which is how a client
tells "the provider was unavailable" apart from "the handbook does not answer this".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


class ProviderError(Exception):
    category = "provider_error"
    retryable = False
    # Set by the pipeline to "retrieval", "generation" or "validation" before re-raising.
    stage = "unknown"


class ProviderNotConfigured(ProviderError):
    category = "provider_not_configured"


class ProviderAuthError(ProviderError):
    category = "provider_auth_failed"


class ProviderTimeout(ProviderError):
    category = "provider_timeout"
    retryable = True


class ProviderUnavailable(ProviderError):
    category = "provider_unavailable"
    retryable = True


class ProviderRateLimited(ProviderError):
    category = "provider_rate_limited"
    retryable = True


class ProviderQuotaExceeded(ProviderError):
    """The account has run out of credit; retrying will not help."""

    category = "provider_quota_exceeded"


class ProviderBadRequest(ProviderError):
    category = "provider_bad_request"


class InvalidModelResponse(ProviderError):
    """The provider answered, but not in the required structure."""

    category = "invalid_model_response"


@dataclass(frozen=True)
class SourcePassage:
    """A chunk as supplied to the model. The mock provider uses these directly."""

    source_id: str
    text: str


@dataclass(frozen=True)
class GenerationRequest:
    instructions: str
    prompt: str
    json_schema: dict
    schema_name: str
    max_output_tokens: int
    question: str = ""
    sources: tuple[SourcePassage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    usage: Usage
    # Retries the client made before this reply, and the provider's id for the request,
    # which is what the provider's support team asks for.
    retries: int = 0
    provider_request_id: str | None = None


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: np.ndarray
    input_tokens: int
    retries: int = 0


class TextGenerator(Protocol):
    name: str
    model: str

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> EmbeddingResult: ...
