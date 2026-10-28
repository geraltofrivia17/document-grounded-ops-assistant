"""The answering pipeline: validate, retrieve, generate, check citations, measure.

Two separate checks happen after the model replies:

* Structure: the reply must parse against the answer schema.
* Citations: every cited id must exist and must have been supplied to the model for
  this question. Ids that fail are removed and recorded. An "answered" reply left
  with no valid citation is rejected rather than shown, because nothing would tie
  it to the handbook.

These checks prove that citations point at real, supplied passages. They do not
prove the passages support the answer; that is measured separately in the evaluation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ops_assistant.chunking import Chunk
from ops_assistant.config import ModelPrice, Settings
from ops_assistant.llm.base import (
    GenerationRequest,
    InvalidModelResponse,
    ProviderError,
    SourcePassage,
    TextGenerator,
    Usage,
)
from ops_assistant.prompting import ANSWER_SCHEMA, INSTRUCTIONS, SCHEMA_NAME, build_prompt
from ops_assistant.retrieval.base import RetrievedChunk, Retriever, SearchResult

logger = logging.getLogger(__name__)

Outcome = Literal["answered", "insufficient_evidence", "conflicting_evidence"]
LETTER = re.compile(r"[^\W\d_]")


class InvalidQuestion(ValueError):
    category = "invalid_question"


class UnverifiableAnswer(InvalidModelResponse):
    """The model answered but none of its citations survived validation."""

    category = "answer_not_verifiable"


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str]
    conflict_note: str
    outcome: Outcome


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    doc_id: str
    version: str
    title: str
    heading: str
    text: str
    source: str

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> Citation:
        return cls(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            version=chunk.version,
            title=chunk.title,
            heading=chunk.heading,
            text=chunk.text,
            source=chunk.source,
        )


@dataclass(frozen=True)
class Timings:
    retrieval_ms: float
    generation_ms: float
    total_ms: float


@dataclass(frozen=True)
class AnswerResult:
    question: str
    outcome: Outcome
    answer: str
    conflict_note: str
    citations: list[Citation]
    retrieved: list[RetrievedChunk]
    cited_by_model: list[str]
    invalid_citations: list[str]
    generation_skipped: bool
    retrieval_mode: str
    model: str
    usage: Usage
    embedding_tokens: int
    cost_usd: float | None
    timings: Timings
    # Retries made by the provider client for this question (embedding plus generation).
    provider_retries: int = 0
    provider_request_id: str | None = None
    warnings: list[str] = field(default_factory=list)


def normalise_question(question: str, min_chars: int, max_chars: int) -> str:
    text = " ".join(question.split())
    if len(text) < min_chars:
        raise InvalidQuestion(f"The question must be at least {min_chars} characters")
    if len(text) > max_chars:
        raise InvalidQuestion(f"The question must be at most {max_chars} characters")
    if not LETTER.search(text):
        raise InvalidQuestion("The question must contain words")
    return text


def find_price(prices: dict[str, ModelPrice], model: str) -> ModelPrice | None:
    """Exact match first, then the longest configured name the model id starts with.

    The API can report a dated snapshot such as ``gpt-6-luna-2026-09-22``.
    """
    if model in prices:
        return prices[model]
    matches = [name for name in prices if model.startswith(name)]
    return prices[max(matches, key=len)] if matches else None


def estimate_cost(
    prices: dict[str, ModelPrice],
    model: str,
    usage: Usage,
    embedding_model: str,
    embedding_tokens: int,
) -> float | None:
    total = 0.0
    if usage.input_tokens or usage.output_tokens:
        price = find_price(prices, model)
        if price is None:
            return None
        uncached = usage.input_tokens - usage.cached_input_tokens
        total += (
            uncached * price.input
            + usage.cached_input_tokens * price.cached_input
            + usage.output_tokens * price.output
        ) / 1_000_000
    if embedding_tokens:
        price = find_price(prices, embedding_model)
        if price is None:
            return None
        total += embedding_tokens * price.input / 1_000_000
    return total


def parse_model_answer(text: str) -> ModelAnswer:
    try:
        return ModelAnswer.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as error:
        raise InvalidModelResponse("The model reply did not match the answer schema") from error


def check_citations(
    cited: list[str], supplied: dict[str, Chunk], known_ids: set[str]
) -> tuple[list[Chunk], list[str], list[str]]:
    """Split cited ids into valid chunks and rejected ids, with a warning for each rejection."""
    valid: list[Chunk] = []
    invalid: list[str] = []
    warnings: list[str] = []
    for chunk_id in dict.fromkeys(cited):
        if chunk_id in supplied:
            valid.append(supplied[chunk_id])
        elif chunk_id in known_ids:
            invalid.append(chunk_id)
            warnings.append(f"Removed citation {chunk_id}: not supplied for this question")
        else:
            invalid.append(chunk_id)
            warnings.append(f"Removed citation {chunk_id}: no such passage")
    return valid, invalid, warnings


class AnswerService:
    def __init__(
        self,
        settings: Settings,
        chunks: list[Chunk],
        retriever: Retriever,
        generator: TextGenerator,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.generator = generator
        self.known_ids = {chunk.chunk_id for chunk in chunks}

    def ask(self, question: str, top_k: int | None = None) -> AnswerResult:
        api = self.settings.api
        question = normalise_question(question, api.min_question_chars, api.max_question_chars)
        k = top_k or self.settings.retrieval.top_k
        started = time.perf_counter()

        try:
            search = self.retriever.search(question, k)
        except ProviderError as error:
            error.stage = "retrieval"
            raise
        retrieval_done = time.perf_counter()

        if not search.items:
            # Nothing in the handbook shares a term with the question: answer without a model call.
            return self._result(
                question=question,
                answer=ModelAnswer(
                    answer="The handbook has no passages related to this question.",
                    citations=[],
                    conflict_note="",
                    outcome="insufficient_evidence",
                ),
                search=search,
                valid=[],
                invalid=[],
                warnings=[],
                usage=Usage(),
                model=self.generator.model,
                skipped=True,
                retries=search.embedding_retries,
                provider_request_id=None,
                started=started,
                retrieval_done=retrieval_done,
            )

        request = GenerationRequest(
            instructions=INSTRUCTIONS,
            prompt=build_prompt(question, search.items),
            json_schema=ANSWER_SCHEMA,
            schema_name=SCHEMA_NAME,
            max_output_tokens=self.settings.generation.max_output_tokens,
            question=question,
            sources=tuple(SourcePassage(i.chunk.chunk_id, i.chunk.text) for i in search.items),
        )
        try:
            generation = self.generator.generate(request)
            answer = parse_model_answer(generation.text)
        except ProviderError as error:
            error.stage = "generation"
            raise

        supplied = {item.chunk.chunk_id: item.chunk for item in search.items}
        valid, invalid, warnings = check_citations(answer.citations, supplied, self.known_ids)
        if answer.outcome == "answered" and not valid:
            error = UnverifiableAnswer("The answer cited no passage that was supplied to the model")
            error.stage = "validation"
            raise error
        if answer.outcome == "conflicting_evidence" and len(valid) < 2:
            warnings.append("Conflict reported with fewer than two valid citations")

        return self._result(
            question=question,
            answer=answer,
            search=search,
            valid=valid,
            invalid=invalid,
            warnings=warnings,
            usage=generation.usage,
            model=generation.model,
            skipped=False,
            retries=search.embedding_retries + generation.retries,
            provider_request_id=generation.provider_request_id,
            started=started,
            retrieval_done=retrieval_done,
        )

    def _result(
        self,
        *,
        question: str,
        answer: ModelAnswer,
        search: SearchResult,
        valid: list[Chunk],
        invalid: list[str],
        warnings: list[str],
        usage: Usage,
        model: str,
        skipped: bool,
        retries: int,
        provider_request_id: str | None,
        started: float,
        retrieval_done: float,
    ) -> AnswerResult:
        finished = time.perf_counter()
        cost = estimate_cost(
            self.settings.pricing.models,
            model,
            usage,
            self.settings.embedding.model,
            search.embedding_tokens,
        )
        if cost is None:
            warnings = [*warnings, f"No price configured for model {model}"]
        return AnswerResult(
            question=question,
            outcome=answer.outcome,
            answer=answer.answer,
            conflict_note=answer.conflict_note,
            citations=[Citation.from_chunk(chunk) for chunk in valid],
            retrieved=search.items,
            cited_by_model=list(answer.citations),
            invalid_citations=invalid,
            generation_skipped=skipped,
            retrieval_mode=self.retriever.name,
            model=model,
            usage=usage,
            embedding_tokens=search.embedding_tokens,
            cost_usd=cost,
            provider_retries=retries,
            provider_request_id=provider_request_id,
            timings=Timings(
                retrieval_ms=(retrieval_done - started) * 1000,
                generation_ms=(finished - retrieval_done) * 1000,
                total_ms=(finished - started) * 1000,
            ),
            warnings=warnings,
        )
