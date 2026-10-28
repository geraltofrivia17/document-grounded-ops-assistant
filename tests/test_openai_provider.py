"""The OpenAI adapter, tested against a fake client object. No network calls."""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from ops_assistant.config import Settings
from ops_assistant.llm.base import GenerationRequest, InvalidModelResponse, ProviderNotConfigured
from ops_assistant.llm.openai_provider import (
    OpenAIEmbedder,
    OpenAIGenerator,
    create_client,
    translate_error,
)

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def response(status_code: int) -> httpx2.Response:
    return httpx2.Response(status_code, request=REQUEST)


def fake_response(status="completed", text='{"ok": true}'):
    usage = SimpleNamespace(
        input_tokens=1200,
        output_tokens=80,
        input_tokens_details=SimpleNamespace(cached_tokens=200),
        output_tokens_details=SimpleNamespace(reasoning_tokens=30),
    )
    return SimpleNamespace(
        status=status,
        output_text=text,
        model="gpt-6-luna-2026-09-22",
        usage=usage,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )


class FakeRaw:
    """Stands in for the SDK's raw response wrapper."""

    def __init__(self, parsed, retries: int = 0, request_id: str = "req_test123"):
        self._parsed = parsed
        self.retries_taken = retries
        self.request_id = request_id

    def parse(self):
        return self._parsed


class FakeEndpoint:
    """Mimics client.responses / client.embeddings, reached through .with_raw_response."""

    def __init__(self, result, retries: int = 0):
        self.result = result
        self.retries = retries
        self.calls: list[dict] = []
        self.with_raw_response = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return FakeRaw(self.result, self.retries)


FakeResponses = FakeEndpoint


def request() -> GenerationRequest:
    return GenerationRequest(
        instructions="rules",
        prompt="<sources/>",
        json_schema={"type": "object"},
        schema_name="handbook_answer",
        max_output_tokens=300,
    )


def test_generate_sends_strict_schema_and_reads_usage() -> None:
    responses = FakeResponses(fake_response())
    generator = OpenAIGenerator(SimpleNamespace(responses=responses), "gpt-6-luna")
    result = generator.generate(request())
    call = responses.calls[0]
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["store"] is False
    assert "reasoning" not in call
    assert result.text == '{"ok": true}'
    assert result.model == "gpt-6-luna-2026-09-22"
    assert (result.usage.input_tokens, result.usage.cached_input_tokens) == (1200, 200)
    assert (result.usage.output_tokens, result.usage.reasoning_tokens) == (80, 30)
    assert result.provider_request_id == "req_test123"
    assert result.retries == 0
    assert "timeout" not in call


def test_retries_and_timeout_are_passed_through() -> None:
    responses = FakeEndpoint(fake_response(), retries=1)
    result = OpenAIGenerator(SimpleNamespace(responses=responses), "m", timeout=12).generate(
        request()
    )
    assert result.retries == 1
    assert responses.calls[0]["timeout"] == 12


def test_reasoning_effort_is_sent_only_when_configured() -> None:
    responses = FakeResponses(fake_response())
    OpenAIGenerator(SimpleNamespace(responses=responses), "m", reasoning_effort="low").generate(
        request()
    )
    assert responses.calls[0]["reasoning"] == {"effort": "low"}


def test_incomplete_response_is_invalid() -> None:
    responses = FakeResponses(fake_response(status="incomplete"))
    with pytest.raises(InvalidModelResponse, match="max_output_tokens"):
        OpenAIGenerator(SimpleNamespace(responses=responses), "m").generate(request())


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (openai.APITimeoutError(request=REQUEST), "provider_timeout"),
        (openai.APIConnectionError(request=REQUEST), "provider_unavailable"),
        (
            openai.AuthenticationError("no", response=response(401), body=None),
            "provider_auth_failed",
        ),
        (
            openai.PermissionDeniedError("no", response=response(403), body=None),
            "provider_auth_failed",
        ),
        (openai.RateLimitError("slow", response=response(429), body=None), "provider_rate_limited"),
        (
            openai.RateLimitError(
                "empty", response=response(429), body={"code": "insufficient_quota"}
            ),
            "provider_quota_exceeded",
        ),
        (
            openai.InternalServerError("oops", response=response(500), body=None),
            "provider_unavailable",
        ),
        (
            openai.APIStatusError("gateway", response=response(502), body=None),
            "provider_unavailable",
        ),
        (openai.BadRequestError("bad", response=response(400), body=None), "provider_bad_request"),
        (
            openai.NotFoundError("no model", response=response(404), body=None),
            "provider_bad_request",
        ),
    ],
)
def test_sdk_errors_are_translated(error: openai.OpenAIError, category: str) -> None:
    assert translate_error(error).category == category
    responses = FakeResponses(error)
    with pytest.raises(Exception) as caught:
        OpenAIGenerator(SimpleNamespace(responses=responses), "m").generate(request())
    assert caught.value.category == category


def test_missing_api_key_is_a_configuration_error(settings: Settings) -> None:
    with pytest.raises(ProviderNotConfigured, match="OPENAI_API_KEY"):
        create_client(settings, environ={})
    with pytest.raises(ProviderNotConfigured):
        create_client(settings, environ={"OPENAI_API_KEY": "   "})


def test_client_uses_configured_timeout_and_retries(settings: Settings) -> None:
    client = create_client(settings, environ={"OPENAI_API_KEY": "sk-test-not-real"})
    assert client.timeout == settings.generation.timeout_seconds
    assert client.max_retries == settings.generation.max_retries


def test_embedder_orders_by_index_and_counts_tokens() -> None:
    data = [
        SimpleNamespace(index=1, embedding=[0.0, 1.0]),
        SimpleNamespace(index=0, embedding=[1.0, 0.0]),
    ]
    fake = SimpleNamespace(data=data, usage=SimpleNamespace(prompt_tokens=9))
    embeddings = FakeEndpoint(fake, retries=1)
    embedder = OpenAIEmbedder(SimpleNamespace(embeddings=embeddings), "text-embedding-3-small", 5)
    result = embedder.embed(["a", "b"])
    assert result.vectors.tolist() == [[1.0, 0.0], [0.0, 1.0]]
    assert result.input_tokens == 9
    assert result.retries == 1
    assert embeddings.calls[0]["timeout"] == 5
