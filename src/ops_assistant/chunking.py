"""Split effective documents into traceable chunks.

Two strategies are supported so that chunking can be compared on the same questions:

``section``
    Chunks never cross a numbered section. A section longer than ``max_words`` is
    split into several chunks. IDs look like ``HR-201:v4.0:s4:c1``.
``window``
    Fixed-size windows run across the whole document and may cover several
    sections. IDs look like ``HR-201:v4.0:w2``.

Either way each chunk records the sections it covers, so evidence labels such as
``HR-201#4`` (document and section) stay comparable across strategies and sizes.

Text is cut into units (paragraphs, list items, table rows) so that a table row or
bullet is never split in the middle unless a single unit is longer than the chunk size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ops_assistant.corpus import Document, EffectiveCorpus

SECTION_HEADING = re.compile(r"^##\s+(?:(\d+)\.\s+)?(.+?)\s*$")
LINE_UNIT = re.compile(r"^\s*(?:\||[-*]\s|\d+\.\s)")

Strategy = Literal["section", "window"]


@dataclass(frozen=True)
class Section:
    number: str
    title: str
    body: str


@dataclass(frozen=True)
class Unit:
    section: Section
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    version: str
    title: str
    sections: tuple[str, ...]
    section_titles: tuple[str, ...]
    text: str
    source: str

    @property
    def evidence_keys(self) -> frozenset[str]:
        """Section-level labels (``DOC-ID#section``) used by the evaluation sets."""
        return frozenset(f"{self.doc_id}#{number}" for number in self.sections)

    @property
    def heading(self) -> str:
        return f"{self.title} > " + " / ".join(
            f"{n}. {t}" for n, t in zip(self.sections, self.section_titles, strict=True)
        )

    @property
    def search_text(self) -> str:
        """Text given to the retrievers: headings add words the body often leaves out."""
        return f"{self.heading}\n{self.text}"


def split_sections(body: str) -> list[Section]:
    sections: list[Section] = []
    number, title, lines = "0", "", []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            sections.append(Section(number=number, title=title, body=text))

    for line in body.splitlines():
        if line.startswith("# "):
            continue
        match = SECTION_HEADING.match(line)
        if match:
            flush()
            number = match.group(1) or str(len(sections) + 1)
            title, lines = match.group(2), []
        else:
            lines.append(line)
    flush()
    return sections


def split_units(section: Section, max_words: int, overlap_words: int) -> list[Unit]:
    """Paragraphs stay whole; list items and table rows become one unit per line.

    A unit longer than max_words is cut into overlapping word windows.
    """
    texts: list[str] = []
    for paragraph in re.split(r"\n\s*\n", section.body):
        lines = [line for line in paragraph.splitlines() if line.strip()]
        if lines and all(LINE_UNIT.match(line) for line in lines):
            texts.extend(line.strip() for line in lines)
        elif lines:
            texts.append(" ".join(line.strip() for line in lines))

    units: list[Unit] = []
    step = max_words - overlap_words
    for text in texts:
        words = text.split()
        if len(words) <= max_words:
            units.append(Unit(section, text))
            continue
        for start in range(0, len(words) - overlap_words, step):
            units.append(Unit(section, " ".join(words[start : start + max_words])))
    return units


def pack_units(units: list[Unit], max_words: int, overlap_words: int) -> list[list[Unit]]:
    """Greedily pack units into groups of at most max_words, carrying trailing units as overlap."""
    groups: list[list[Unit]] = []
    current: list[Unit] = []
    for unit in units:
        if current and sum(u.words for u in current) + unit.words > max_words:
            groups.append(current)
            carry: list[Unit] = []
            for previous in reversed(current):
                if sum(u.words for u in carry) + previous.words > overlap_words:
                    break
                carry.insert(0, previous)
            current = carry
        current.append(unit)
    if current:
        groups.append(current)
    return groups


def _make_chunk(document: Document, chunk_id: str, units: list[Unit]) -> Chunk:
    sections: list[Section] = []
    for unit in units:
        if unit.section not in sections:
            sections.append(unit.section)
    meta = document.metadata
    return Chunk(
        chunk_id=chunk_id,
        doc_id=meta.doc_id,
        version=meta.version,
        title=meta.title,
        sections=tuple(s.number for s in sections),
        section_titles=tuple(s.title for s in sections),
        text="\n".join(unit.text for unit in units),
        source=meta.source,
    )


def chunk_document(
    document: Document, max_words: int, overlap_words: int, strategy: Strategy = "section"
) -> list[Chunk]:
    meta = document.metadata
    prefix = f"{meta.doc_id}:v{meta.version}"
    sections = split_sections(document.body)
    if strategy == "window":
        units = [u for s in sections for u in split_units(s, max_words, overlap_words)]
        groups = pack_units(units, max_words, overlap_words)
        return [_make_chunk(document, f"{prefix}:w{i}", g) for i, g in enumerate(groups, 1)]

    chunks: list[Chunk] = []
    for section in sections:
        groups = pack_units(
            split_units(section, max_words, overlap_words), max_words, overlap_words
        )
        for index, group in enumerate(groups, start=1):
            chunk_id = f"{prefix}:s{section.number}:c{index}"
            chunks.append(_make_chunk(document, chunk_id, group))
    return chunks


def chunk_corpus(
    corpus: EffectiveCorpus, max_words: int, overlap_words: int, strategy: Strategy = "section"
) -> list[Chunk]:
    chunks = [
        chunk
        for document in corpus.documents
        for chunk in chunk_document(document, max_words, overlap_words, strategy)
    ]
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk IDs are not unique; check for repeated section numbers")
    return chunks
