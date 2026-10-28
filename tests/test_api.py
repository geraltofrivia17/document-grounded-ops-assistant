from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from ops_assistant.api import create_app
from ops_assistant.config import Settings
from ops_assistant.llm.base import (
    InvalidModelResponse,
    ProviderError,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from ops_assistant.llm.mock import MockGenerator
from ops_assistant.service import Pipeline
from tests.helpers import reply

QUESTION = {"question": "What mileage rate can I claim for my own car?"}


@pytest.fixture
def client(make_pipeline: Callable[..., Pipeline]) -> Callable[..., TestClient]:
    def factory(generator: MockGenerator | None = None) -> TestClient:
        return TestClient(create_app(make_pipeline(generator)), raise_server_exceptions=False)

    return factory


def test_health_reports_configuration(client) -> None:
    response = client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["documents"] == 16
    assert body["excluded_versions"] == 3
    assert body["retrieval_mode"] == "keyword"
    assert body["provider"] == "mock"


def test_ask_returns_answer_citations_and_measurements(client) -> None:
    response = client().post("/ask", json=QUESTION)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "answered"
    assert body["citations"][0]["id"] == "HR-201:v4.0:s4:c1"
    assert body["citations"][0]["section"] == "4. Mileage"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert set(body["timings"]) == {"retrieval_ms", "generation_ms", "total_ms"}
    assert body["usage"]["estimated_cost_usd"] == 0
    assert body["provider"] == {"request_id": None, "retries": 0}
    assert len(body["retrieved"]) == 5


def test_request_id_is_echoed_when_valid(client) -> None:
    response = client().post("/ask", json=QUESTION, headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.json()["request_id"] == "abc-123"


def test_unsafe_request_id_is_replaced(client) -> None:
    response = client().post(
        "/ask", json=QUESTION, headers={"X-Request-ID": "bad id\nwith newline"}
    )
    assert response.headers["X-Request-ID"] != "bad id\nwith newline"
    assert len(response.headers["X-Request-ID"]) == 16


@pytest.mark.parametrize(
    ("payload", "category"),
    [
        ({"question": ""}, "invalid_request"),
        ({}, "invalid_request"),
        ({"question": 42}, "invalid_request"),
        ({"question": "What?", "top_k": 0}, "invalid_request"),
        ({"question": "What?", "extra": True}, "invalid_request"),
        ({"question": "    "}, "invalid_question"),
        ({"question": "x" * 600}, "invalid_question"),
    ],
)
def test_invalid_input_is_rejected_with_a_category(client, payload: dict, category: str) -> None:
    response = client().post("/ask", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["category"] == category


def test_malformed_json_body(client) -> None:
    response = client().post(
        "/ask", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["category"] == "invalid_request"


@pytest.mark.parametrize(
    ("error", "status", "category"),
    [
        (ProviderTimeout("slow"), 504, "provider_timeout"),
        (ProviderUnavailable("down"), 503, "provider_unavailable"),
        (ProviderRateLimited("busy"), 503, "provider_rate_limited"),
        (ProviderQuotaExceeded("empty"), 503, "provider_quota_exceeded"),
        (InvalidModelResponse("bad"), 502, "invalid_model_response"),
        (ProviderError("odd"), 502, "provider_error"),
    ],
)
def test_provider_failures_map_to_status_and_category(client, error, status, category) -> None:
    response = client(MockGenerator(failure=error)).post("/ask", json=QUESTION)
    assert response.status_code == status
    body = response.json()["error"]
    assert body["category"] == category
    assert body["stage"] == "generation"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_unverifiable_answer_is_not_shown(client) -> None:
    generator = MockGenerator(script=lambda r: reply("Made up.", ["NOPE-001:v1.0:s1:c1"]))
    response = client(generator).post("/ask", json=QUESTION)
    assert response.status_code == 502
    assert response.json()["error"]["category"] == "answer_not_verifiable"
    assert "Made up" not in response.text


def test_abstention_is_a_normal_response_not_an_error(client) -> None:
    generator = MockGenerator(script=lambda r: reply("Not covered.", [], "insufficient_evidence"))
    response = client(generator).post("/ask", json={"question": "What is the pension scheme?"})
    assert response.status_code == 200
    assert response.json()["outcome"] == "insufficient_evidence"


def test_unexpected_error_returns_500_with_request_id(client) -> None:
    def broken(request):
        raise RuntimeError("bug")

    response = client(MockGenerator(script=broken)).post("/ask", json=QUESTION)
    assert response.status_code == 500
    assert response.json()["error"]["category"] == "internal_error"
    assert "X-Request-ID" in response.headers
    assert "bug" not in response.text


def test_service_without_api_key_starts_and_explains(settings: Settings) -> None:
    app = create_app(settings=settings.with_overrides(generation={"provider": "openai"}))
    with TestClient(app) as unconfigured:
        health = unconfigured.get("/health")
        assert health.status_code == 503
        assert "OPENAI_API_KEY" in health.json()["reason"]
        ask = unconfigured.post("/ask", json=QUESTION)
        assert ask.status_code == 503
        assert ask.json()["error"]["category"] == "provider_not_configured"


def test_demo_page_is_served(client) -> None:
    response = client().get("/")
    assert response.status_code == 200
    assert "Operations Assistant" in response.text
