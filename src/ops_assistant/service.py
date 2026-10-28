"""Assemble an AnswerService from settings.

Kept apart from the API so the CLI, the evaluation and the tests build the pipeline
the same way, and so tests can inject a mock generator or an offline embedder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ops_assistant.answer import AnswerService
from ops_assistant.chunking import Chunk, chunk_corpus
from ops_assistant.config import RetrievalMode, Settings
from ops_assistant.corpus import EffectiveCorpus, load_effective_corpus
from ops_assistant.llm.base import Embedder, ProviderNotConfigured, TextGenerator
from ops_assistant.llm.mock import MockGenerator
from ops_assistant.llm.openai_provider import build_openai
from ops_assistant.retrieval import build_retriever, needs_embeddings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pipeline:
    settings: Settings
    corpus: EffectiveCorpus
    chunks: list[Chunk]
    service: AnswerService


def load_chunks(settings: Settings) -> tuple[EffectiveCorpus, list[Chunk]]:
    corpus = load_effective_corpus(settings.handbook_dir, settings.corpus.as_of)
    chunking = settings.chunking
    chunks = chunk_corpus(corpus, chunking.max_words, chunking.overlap_words, chunking.strategy)
    logger.info(
        "Loaded %d effective documents (%d versions excluded) into %d chunks",
        len(corpus.documents),
        len(corpus.exclusions),
        len(chunks),
    )
    return corpus, chunks


def resolve_providers(
    settings: Settings,
    generator: TextGenerator | None = None,
    embedder: Embedder | None = None,
) -> tuple[TextGenerator, Embedder | None]:
    """Use injected providers when given, otherwise build them from settings."""
    wants_embeddings = needs_embeddings(settings.retrieval.mode)
    if settings.generation.provider == "mock":
        if wants_embeddings and embedder is None:
            raise ProviderNotConfigured(
                f"Retrieval mode '{settings.retrieval.mode}' needs OpenAI embeddings. "
                "The mock provider only supports OPS_RETRIEVAL_MODE=keyword."
            )
        return generator or MockGenerator(), embedder
    if generator is None or (wants_embeddings and embedder is None):
        openai_generator, openai_embedder = build_openai(settings)
        generator = generator or openai_generator
        embedder = embedder or openai_embedder
    return generator, embedder if wants_embeddings else None


def build_pipeline(
    settings: Settings,
    generator: TextGenerator | None = None,
    embedder: Embedder | None = None,
    mode: RetrievalMode | None = None,
    query_embedder: Embedder | None = None,
) -> Pipeline:
    if mode is not None:
        settings = settings.with_overrides(retrieval={"mode": mode})
    corpus, chunks = load_chunks(settings)
    generator, embedder = resolve_providers(settings, generator, embedder)
    retriever = build_retriever(settings, chunks, embedder, query_embedder=query_embedder)
    service = AnswerService(settings, chunks, retriever, generator)
    return Pipeline(settings=settings, corpus=corpus, chunks=chunks, service=service)
