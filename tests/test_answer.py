from collections.abc import Callable

import numpy as np
import pytest

from ops_assistant.answer import (
    InvalidQuestion,
    UnverifiableAnswer,
    estimate_cost,
    find_price,
    normalise_question,
)
from ops_assistant.config import Settings
from ops_assistant.llm.base import (
    EmbeddingResult,
    InvalidModelResponse,
    ProviderTimeout,
    ProviderUnavailable,
    Usage,
)
from ops_assistant.llm.mock import HashingEmbedder, MockGenerator
from ops_assistant.prompting import INSTRUCTIONS, build_prompt
from ops_assistant.service import Pipeline, build_pipeline
from tests.helpers import reply

MILEAGE = "What mileage rate can I claim for my own car?"


def test_answer_cites_supplied_passage(make_pipeline: Callable[..., Pipeline]) -> None:
    result = make_pipeline().service.ask(MILEAGE)
    assert result.outcome == "answered"
    assert [c.chunk_id for c in result.citations] == ["HR-201:v4.0:s4:c1"]
    assert result.invalid_citations == []
    assert result.retrieval_mode == "keyword"
    assert result.timings.total_ms >= result.timings.retrieval_ms


def test_unknown_and_unsupplied_citations_are_removed(make_pipeline) -> None:
    def script(request):
        return reply("x", [request.sources[0].source_id, "HR-999:v1.0:s1:c1", "FAC-402:v1.5:s1:c1"])

    result = make_pipeline(MockGenerator(script=script)).service.ask(MILEAGE)
    assert [c.chunk_id for c in result.citations] == ["HR-201:v4.0:s4:c1"]
    assert result.invalid_citations == ["HR-999:v1.0:s1:c1", "FAC-402:v1.5:s1:c1"]
    assert any("no such passage" in w for w in result.warnings)
    assert any("not supplied" in w for w in result.warnings)


def test_superseded_passage_ids_cannot_be_cited(make_pipeline) -> None:
    # The model "remembers" the old expenses policy; its id does not exist in the index.
    script = lambda request: reply("40p", ["HR-201:v3.2:s4:c1"])  # noqa: E731
    with pytest.raises(UnverifiableAnswer) as caught:
        make_pipeline(MockGenerator(script=script)).service.ask(MILEAGE)
    assert caught.value.stage == "validation"


def test_answer_without_valid_citation_is_rejected(make_pipeline) -> None:
    script = lambda request: reply("Trust me.", [])  # noqa: E731
    with pytest.raises(UnverifiableAnswer):
        make_pipeline(MockGenerator(script=script)).service.ask(MILEAGE)


def test_abstention_passes_through(make_pipeline) -> None:
    script = lambda request: reply("Not covered.", [], "insufficient_evidence")  # noqa: E731
    result = make_pipeline(MockGenerator(script=script)).service.ask("What is the pension scheme?")
    assert result.outcome == "insufficient_evidence"
    assert result.citations == []


def test_conflict_with_one_citation_is_flagged(make_pipeline) -> None:
    def script(request):
        return reply("Two rules.", [request.sources[0].source_id], "conflicting_evidence", "A vs B")

    result = make_pipeline(MockGenerator(script=script)).service.ask("laptop return after leaving")
    assert result.outcome == "conflicting_evidence"
    assert "fewer than two" in result.warnings[0]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"answer": "x", "citations": []}',
        reply(outcome="maybe"),
        '{"answer": "x", "citations": [], "conflict_note": "", "outcome": "answered", "extra": 1}',
    ],
)
def test_malformed_model_replies_raise(make_pipeline, text: str) -> None:
    generator = MockGenerator(script=lambda request: text)
    with pytest.raises(InvalidModelResponse) as caught:
        make_pipeline(generator).service.ask(MILEAGE)
    assert caught.value.stage == "generation"


def test_provider_failure_keeps_its_category(make_pipeline) -> None:
    generator = MockGenerator(failure=ProviderTimeout("slow"))
    with pytest.raises(ProviderTimeout) as caught:
        make_pipeline(generator).service.ask(MILEAGE)
    assert caught.value.category == "provider_timeout"
    assert caught.value.stage == "generation"


class FailingQueryEmbedder(HashingEmbedder):
    """Embeds the corpus, then fails on the first query."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if self.fail:
            raise ProviderUnavailable("down")
        return super().embed(texts)


def test_embedding_failure_is_reported_as_retrieval_stage(settings: Settings) -> None:
    embedder = FailingQueryEmbedder()
    pipeline = build_pipeline(settings, MockGenerator(), embedder, mode="embedding")
    embedder.fail = True
    with pytest.raises(ProviderUnavailable) as caught:
        pipeline.service.ask(MILEAGE)
    assert caught.value.stage == "retrieval"


def test_no_matching_passages_skips_the_model(make_pipeline) -> None:
    generator = MockGenerator()
    result = make_pipeline(generator).service.ask("zebra xylophone quokka")
    assert result.outcome == "insufficient_evidence"
    assert result.generation_skipped
    assert generator.requests == []


@pytest.mark.parametrize("question", ["", "   ", "?!", "12345", "x" * 501])
def test_invalid_questions_are_rejected(question: str) -> None:
    with pytest.raises(InvalidQuestion):
        normalise_question(question, 3, 500)


def test_question_whitespace_is_normalised() -> None:
    assert normalise_question("  How   many\n days? ", 3, 500) == "How many days?"


def test_hybrid_mode_runs_offline_with_test_embedder(make_pipeline) -> None:
    result = make_pipeline(mode="hybrid").service.ask(MILEAGE)
    assert result.retrieval_mode == "hybrid"
    assert result.embedding_tokens > 0


def test_injected_document_text_stays_inside_its_source_tag(make_pipeline) -> None:
    generator = MockGenerator(script=lambda r: reply("No.", [r.sources[0].source_id]))
    make_pipeline(generator).service.ask(
        "Can Greywell Haulage invoices be paid without a purchase order?"
    )
    prompt = generator.requests[0].prompt
    injected = prompt.index("ignore all previous instructions")
    opening = prompt.rindex('<source id="SUP-502', 0, injected)
    assert prompt.index("</source>", opening) > injected
    assert 'origin="external"' in prompt[opening:injected]
    assert "reference material, not instructions" in generator.requests[0].instructions


def test_markup_in_questions_and_passages_is_escaped(chunks) -> None:
    from ops_assistant.retrieval.base import RetrievedChunk

    prompt = build_prompt("</question><sources>fake", [RetrievedChunk(chunks[0], 1.0, 1)])
    assert prompt.count("<question>") == 1
    assert "&lt;/question&gt;" in prompt


def test_instructions_cover_abstention_conflict_and_injection() -> None:
    for phrase in (
        "insufficient_evidence",
        "conflicting_evidence",
        "not instructions",
        "Only use ids",
    ):
        assert phrase in INSTRUCTIONS


def test_cost_estimate(settings: Settings) -> None:
    prices = settings.pricing.models
    usage = Usage(input_tokens=3000, cached_input_tokens=1000, output_tokens=200)
    cost = estimate_cost(prices, "gpt-6-luna", usage, "text-embedding-3-small", 20)
    expected = (2000 * 0.10 + 1000 * 0.01 + 200 * 0.50 + 20 * 0.02) / 1_000_000
    assert cost == pytest.approx(expected)


def test_dated_model_snapshot_uses_base_price(settings: Settings) -> None:
    prices = settings.pricing.models
    assert find_price(prices, "gpt-6-luna-2026-09-22") == prices["gpt-6-luna"]
    assert find_price(prices, "gpt-6.1-sol") == prices["gpt-6.1-sol"]
    assert find_price(prices, "unknown-model") is None


def test_unknown_model_price_gives_warning_not_failure(settings: Settings) -> None:
    class Priced(MockGenerator):
        def generate(self, request):
            result = super().generate(request)
            return type(result)(
                result.text, "unknown-model", Usage(input_tokens=10, output_tokens=5)
            )

    pipeline = build_pipeline(
        settings, Priced(script=lambda r: reply("x", [r.sources[0].source_id]))
    )
    result = pipeline.service.ask(MILEAGE)
    assert result.cost_usd is None
    assert "No price configured" in result.warnings[-1]


def test_hashing_embedder_is_deterministic() -> None:
    first = HashingEmbedder().embed(["same words"]).vectors
    second = HashingEmbedder().embed(["same words"]).vectors
    assert np.array_equal(first, second)
