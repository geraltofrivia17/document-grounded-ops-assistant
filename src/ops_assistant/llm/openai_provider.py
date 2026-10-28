"""OpenAI implementations of the generation and embedding interfaces.

Generation uses the Responses API with Structured Outputs (a strict JSON schema), so
the model's answer either matches the schema or the call fails in a way we can see.
``store=False`` asks OpenAI not to keep the response for later retrieval.

All SDK exceptions are translated into ProviderError subclasses here, so nothing
outside this module needs to import ``openai``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np
import openai

from ops_assistant.config import Settings
from ops_assistant.llm.base import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    InvalidModelResponse,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderNotConfigured,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    Usage,
)

API_KEY_VARIABLE = "OPENAI_API_KEY"


def create_client(settings: Settings, environ: dict[str, str] | None = None) -> openai.OpenAI:
    environ = dict(os.environ) if environ is None else environ
    api_key = environ.get(API_KEY_VARIABLE, "").strip()
    if not api_key:
        raise ProviderNotConfigured(
            f"{API_KEY_VARIABLE} is not set. Set it, or run with OPS_PROVIDER=mock "
            "and OPS_RETRIEVAL_MODE=keyword to use the offline mock."
        )
    return openai.OpenAI(
        api_key=api_key,
        timeout=settings.generation.timeout_seconds,
        max_retries=settings.generation.max_retries,
    )


def translate_error(error: openai.OpenAIError) -> ProviderError:
    """Map an SDK exception to the error category reported by the API."""
    # Order matters: APITimeoutError is a subclass of APIConnectionError.
    if isinstance(error, openai.APITimeoutError):
        return ProviderTimeout("The model provider did not respond in time")
    if isinstance(error, openai.APIConnectionError):
        return ProviderUnavailable("Could not connect to the model provider")
    if isinstance(error, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthError("The provider rejected the API key")
    if isinstance(error, openai.RateLimitError):
        if getattr(error, "code", None) == "insufficient_quota":
            return ProviderQuotaExceeded("The provider account has no remaining credit")
        return ProviderRateLimited("The provider is rate limiting requests")
    if isinstance(error, openai.InternalServerError):
        return ProviderUnavailable("The model provider returned a server error")
    if isinstance(
        error, openai.BadRequestError | openai.NotFoundError | openai.UnprocessableEntityError
    ):
        return ProviderBadRequest(f"The provider rejected the request: {error}")
    if isinstance(error, openai.APIStatusError) and error.status_code >= 500:
        return ProviderUnavailable(f"The model provider returned HTTP {error.status_code}")
    return ProviderError(f"Unexpected provider error: {error}")


@contextmanager
def provider_errors() -> Iterator[None]:
    try:
        yield
    except openai.OpenAIError as error:
        raise translate_error(error) from error


def _usage_from(response: Any) -> Usage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return Usage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=getattr(input_details, "cached_tokens", 0) or 0,
        output_tokens=usage.output_tokens,
        reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0,
    )


class OpenAIGenerator:
    name = "openai"

    def __init__(
        self, client: Any, model: str, reasoning_effort: str = "", timeout: float | None = None
    ) -> None:
        self._client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout

    def generate(self, request: GenerationRequest) -> GenerationResult:
        options: dict[str, Any] = {}
        if self.reasoning_effort:
            options["reasoning"] = {"effort": self.reasoning_effort}
        if self.timeout is not None:
            options["timeout"] = self.timeout
        # with_raw_response exposes how many retries the SDK made and OpenAI's own request id.
        with provider_errors():
            raw = self._client.responses.with_raw_response.create(
                model=self.model,
                instructions=request.instructions,
                input=request.prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": request.schema_name,
                        "schema": request.json_schema,
                        "strict": True,
                    }
                },
                max_output_tokens=request.max_output_tokens,
                store=False,
                **options,
            )
            response = raw.parse()
        if response.status != "completed":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None) or response.status
            raise InvalidModelResponse(f"The model response was not completed ({reason})")
        return GenerationResult(
            text=response.output_text,
            model=response.model,
            usage=_usage_from(response),
            retries=raw.retries_taken,
            provider_request_id=raw.request_id,
        )


class OpenAIEmbedder:
    def __init__(self, client: Any, model: str, timeout: float | None = None) -> None:
        self._client = client
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> EmbeddingResult:
        options = {"timeout": self.timeout} if self.timeout is not None else {}
        with provider_errors():
            raw = self._client.embeddings.with_raw_response.create(
                model=self.model, input=texts, **options
            )
            response = raw.parse()
        rows = sorted(response.data, key=lambda item: item.index)
        vectors = np.array([row.embedding for row in rows], dtype=np.float32)
        return EmbeddingResult(
            vectors=vectors, input_tokens=response.usage.prompt_tokens, retries=raw.retries_taken
        )


ClientFactory = Callable[[Settings], Any]


def build_openai(
    settings: Settings, client_factory: ClientFactory = create_client
) -> tuple[OpenAIGenerator, OpenAIEmbedder]:
    client = client_factory(settings)
    generation = settings.generation
    generator = OpenAIGenerator(
        client, generation.model, generation.reasoning_effort, generation.timeout_seconds
    )
    embedding = settings.embedding
    return generator, OpenAIEmbedder(client, embedding.model, embedding.timeout_seconds)
