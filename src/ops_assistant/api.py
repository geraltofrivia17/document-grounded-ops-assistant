"""FastAPI service: GET /health, POST /ask and a small demo page at GET /.

Every response carries an X-Request-ID header. Errors share one shape,
``{"error": {"category", "message", "stage", "request_id"}}``, and the category says
which part failed. A deliberate refusal to answer is not an error: it is a 200
response with ``outcome = "insufficient_evidence"``.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from importlib import resources

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ops_assistant import __version__
from ops_assistant.answer import AnswerResult, InvalidQuestion
from ops_assistant.config import Settings, load_settings
from ops_assistant.llm.base import ProviderError, ProviderNotConfigured
from ops_assistant.logging_setup import request_id_var
from ops_assistant.service import Pipeline, build_pipeline

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

STATUS_BY_CATEGORY = {
    "invalid_request": 422,
    "invalid_question": 422,
    "provider_not_configured": 503,
    "provider_unavailable": 503,
    "provider_rate_limited": 503,
    "provider_quota_exceeded": 503,
    "provider_timeout": 504,
    "provider_auth_failed": 502,
    "provider_bad_request": 502,
    "invalid_model_response": 502,
    "answer_not_verifiable": 502,
    "provider_error": 502,
    "internal_error": 500,
}


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Loose bounds here; the configured limits are enforced by the answering service.
    question: str = Field(min_length=1, max_length=5000)
    top_k: int | None = Field(default=None, ge=1, le=10)


class CitationOut(BaseModel):
    id: str
    document: str
    version: str
    title: str
    section: str
    origin: str
    text: str


class RetrievedOut(BaseModel):
    id: str
    rank: int
    score: float


class UsageOut(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    embedding_tokens: int
    estimated_cost_usd: float | None


class ProviderOut(BaseModel):
    request_id: str | None
    retries: int


class TimingsOut(BaseModel):
    retrieval_ms: float
    generation_ms: float
    total_ms: float


class AskResponse(BaseModel):
    request_id: str
    outcome: str
    answer: str
    conflict_note: str
    citations: list[CitationOut]
    retrieved: list[RetrievedOut]
    removed_citations: list[str]
    generation_skipped: bool
    model: str
    retrieval_mode: str
    usage: UsageOut
    timings: TimingsOut
    provider: ProviderOut
    warnings: list[str]


def to_response(result: AnswerResult, request_id: str) -> AskResponse:
    return AskResponse(
        request_id=request_id,
        outcome=result.outcome,
        answer=result.answer,
        conflict_note=result.conflict_note,
        citations=[
            CitationOut(
                id=c.chunk_id,
                document=c.doc_id,
                version=c.version,
                title=c.title,
                section=c.heading.split(" > ", 1)[1],
                origin=c.source,
                text=c.text,
            )
            for c in result.citations
        ],
        retrieved=[
            RetrievedOut(id=r.chunk.chunk_id, rank=r.rank, score=round(r.score, 6))
            for r in result.retrieved
        ],
        removed_citations=result.invalid_citations,
        generation_skipped=result.generation_skipped,
        model=result.model,
        retrieval_mode=result.retrieval_mode,
        usage=UsageOut(
            input_tokens=result.usage.input_tokens,
            cached_input_tokens=result.usage.cached_input_tokens,
            output_tokens=result.usage.output_tokens,
            reasoning_tokens=result.usage.reasoning_tokens,
            embedding_tokens=result.embedding_tokens,
            estimated_cost_usd=result.cost_usd,
        ),
        timings=TimingsOut(
            retrieval_ms=round(result.timings.retrieval_ms, 1),
            generation_ms=round(result.timings.generation_ms, 1),
            total_ms=round(result.timings.total_ms, 1),
        ),
        provider=ProviderOut(
            request_id=result.provider_request_id, retries=result.provider_retries
        ),
        warnings=result.warnings,
    )


def error_response(category: str, message: str, stage: str = "request") -> JSONResponse:
    body = {
        "error": {
            "category": category,
            "message": message,
            "stage": stage,
            "request_id": request_id_var.get(),
        }
    }
    return JSONResponse(status_code=STATUS_BY_CATEGORY.get(category, 500), content=body)


def create_app(pipeline: Pipeline | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass a ready pipeline; the server builds one from settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.pipeline is None and app.state.startup_error is None:
            try:
                app.state.pipeline = build_pipeline(settings or load_settings())
            except ProviderNotConfigured as error:
                # Start anyway so /health can explain the problem instead of a crash loop.
                app.state.startup_error = str(error)
                logger.error("Service started without a provider: %s", error)
        yield

    app = FastAPI(
        title="Document-Grounded Operations Assistant", version=__version__, lifespan=lifespan
    )
    app.state.pipeline = pipeline
    app.state.startup_error = None

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Handled here rather than by an app-level handler so the reply still carries
            # the request id header and the id appears in the log line.
            logger.exception("Unhandled error")
            response = error_response("internal_error", "Unexpected server error", "server")
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        # Logged after the reset, so pass the id explicitly.
        logger.info(
            "request",
            extra={
                "fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'body'}: {e['msg']}"
            for e in error.errors()
        )
        return error_response("invalid_request", problems or "The request body is not valid")

    @app.exception_handler(InvalidQuestion)
    async def invalid_question(_: Request, error: InvalidQuestion) -> JSONResponse:
        return error_response(error.category, str(error))

    @app.exception_handler(ProviderError)
    async def provider_failure(_: Request, error: ProviderError) -> JSONResponse:
        logger.warning(
            "ask failed",
            extra={"fields": {"error_category": error.category, "stage": error.stage}},
        )
        return error_response(error.category, str(error), error.stage)

    @app.get("/health")
    def health() -> JSONResponse:
        current: Pipeline | None = app.state.pipeline
        if current is None:
            reason = app.state.startup_error or "Service is starting"
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "reason": reason}
            )
        service = current.service
        return JSONResponse(
            content={
                "status": "ok",
                "version": __version__,
                "provider": service.generator.name,
                "model": service.generator.model,
                "retrieval_mode": service.retriever.name,
                "as_of": current.corpus.as_of.isoformat(),
                "documents": len(current.corpus.documents),
                "excluded_versions": len(current.corpus.exclusions),
                "chunks": len(current.chunks),
            }
        )

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest) -> AskResponse:
        current: Pipeline | None = app.state.pipeline
        if current is None:
            raise ProviderNotConfigured(app.state.startup_error or "Service is starting")
        result = current.service.ask(body.question, body.top_k)
        logger.info(
            "ask",
            extra={
                "fields": {
                    "outcome": result.outcome,
                    # The question is not logged: staff questions can contain personal details.
                    "question_chars": len(result.question),
                    "retrieval_mode": result.retrieval_mode,
                    "model": result.model,
                    "retrieved": [r.chunk.chunk_id for r in result.retrieved],
                    "cited": [c.chunk_id for c in result.citations],
                    "removed_citations": result.invalid_citations,
                    "retrieval_ms": round(result.timings.retrieval_ms, 1),
                    "generation_ms": round(result.timings.generation_ms, 1),
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "estimated_cost_usd": result.cost_usd,
                    "provider_retries": result.provider_retries,
                    "provider_request_id": result.provider_request_id,
                }
            },
        )
        return to_response(result, request_id_var.get())

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def demo_page() -> HTMLResponse:
        page = resources.files("ops_assistant").joinpath("static/index.html").read_text("utf-8")
        return HTMLResponse(page)

    return app
