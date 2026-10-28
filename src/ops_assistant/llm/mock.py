"""Offline stand-ins for the provider, used by the tests and the keyless demo.

``MockGenerator`` never calls a network service. In its default "extractive" mode it
returns the opening sentences of the top-ranked passage and cites it, which is enough
to exercise the API, citation validation and the demo page. It does not reason, so
its answers say nothing about model quality; the evaluation always uses a real model.

``HashingEmbedder`` turns text into a deterministic bag-of-words vector. It exists so
that the embedding and hybrid code paths can be tested without an API key.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

import numpy as np

from ops_assistant.llm.base import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"[a-z0-9£]+")

Script = Callable[[GenerationRequest], str]


def extractive_answer(request: GenerationRequest) -> str:
    if not request.sources:
        payload = {
            "outcome": "insufficient_evidence",
            "answer": "No handbook passages were supplied, so the question cannot be answered.",
            "citations": [],
            "conflict_note": "",
        }
        return json.dumps(payload)
    top = request.sources[0]
    body = top.text.replace("\n", " ")
    sentences = [s for s in SENTENCE_END.split(body) if s.strip()]
    payload = {
        "outcome": "answered",
        "answer": " ".join(sentences[:2]),
        "citations": [top.source_id],
        "conflict_note": "",
    }
    return json.dumps(payload)


class MockGenerator:
    """Deterministic generator.

    ``script`` replaces the extractive behaviour with a function of the request, and
    ``failure`` makes every call raise the given ProviderError, which is how the tests
    simulate timeouts and outages.
    """

    name = "mock"

    def __init__(self, script: Script | None = None, failure: ProviderError | None = None) -> None:
        self.model = "mock-extractive" if script is None else "mock-scripted"
        self._script = script or extractive_answer
        self._failure = failure
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self._failure is not None:
            raise self._failure
        return GenerationResult(text=self._script(request), model=self.model, usage=Usage())


class HashingEmbedder:
    """Bag-of-words vectors via the hashing trick. Deterministic and offline; for tests only."""

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions
        self.model = f"hashing-{dimensions}"
        self.calls = 0

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls += 1
        vectors = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in WORD.findall(text.lower()):
                bucket = (
                    int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest())
                    % self.dimensions
                )
                vectors[row, bucket] += 1.0
        tokens = sum(len(WORD.findall(t.lower())) for t in texts)
        return EmbeddingResult(vectors=vectors, input_tokens=tokens)
