"""BM25 keyword retrieval, written out in full so every scoring step can be explained."""

from __future__ import annotations

import math
import re
from collections import Counter

import snowballstemmer

from ops_assistant.chunking import Chunk
from ops_assistant.retrieval.base import SearchResult, rank_top

TOKEN = re.compile(r"[a-z0-9£]+")

# A short list: common function words only. Words like "not", "no" and "without"
# are kept because they change the meaning of policy questions.
STOPWORDS = frozenset(
    """
    a an and are as at be been by can could do does for from had has have how i if in
    into is it its me my of on or our should so than that the their them then there these
    they this to us was we were what when where which who why will with would you your
    """.split()  # noqa: SIM905 - easier to read and edit as text
)


class Tokenizer:
    def __init__(self, stemming: bool = True) -> None:
        self._stemmer = snowballstemmer.stemmer("english") if stemming else None

    def __call__(self, text: str) -> list[str]:
        tokens = [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]
        if self._stemmer is None:
            return tokens
        return self._stemmer.stemWords(tokens)


class BM25Retriever:
    """Okapi BM25 with the usual defaults k1=1.5, b=0.75.

    The IDF uses log(1 + (N - df + 0.5) / (df + 0.5)), which stays positive even for
    terms found in more than half of the chunks.
    """

    name = "keyword"

    def __init__(
        self, chunks: list[Chunk], stemming: bool = True, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.chunks = chunks
        self.tokenize = Tokenizer(stemming)
        self.k1, self.b = k1, b
        self._term_counts = [Counter(self.tokenize(c.search_text)) for c in chunks]
        self._lengths = [sum(counts.values()) for counts in self._term_counts]
        self._average_length = sum(self._lengths) / max(len(chunks), 1)
        document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            document_frequency.update(counts.keys())
        total = len(chunks)
        self._idf = {
            term: math.log(1 + (total - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    def scores(self, query: str) -> list[float]:
        terms = self.tokenize(query)
        results = []
        for counts, length in zip(self._term_counts, self._lengths, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self._average_length)
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    score += self._idf[term] * tf * (self.k1 + 1) / (tf + norm)
            results.append(score)
        return results

    def search(self, query: str, k: int) -> SearchResult:
        scores = self.scores(query)
        # A chunk sharing no terms with the query is not evidence, so it is never returned.
        matched = [i for i, s in enumerate(scores) if s > 0]
        ranked = rank_top([self.chunks[i] for i in matched], [scores[i] for i in matched], k)
        return SearchResult(items=ranked)
