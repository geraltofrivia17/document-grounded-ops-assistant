import re

from ops_assistant.chunking import Chunk, Section, chunk_corpus, pack_units, split_units
from ops_assistant.config import Settings
from ops_assistant.corpus import load_effective_corpus

SECTION_ID = re.compile(r"^[A-Z]{2,4}-\d{3}:v\d+\.\d+:s\d+:c\d+$")
WINDOW_ID = re.compile(r"^[A-Z]{2,4}-\d{3}:v\d+\.\d+:w\d+$")


def test_section_chunk_ids_are_unique_and_traceable(chunks: list[Chunk]) -> None:
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    for chunk in chunks:
        assert SECTION_ID.match(chunk.chunk_id)
        assert len(chunk.sections) == 1
        assert chunk.chunk_id.startswith(f"{chunk.doc_id}:v{chunk.version}:s{chunk.sections[0]}:")


def test_window_chunks_record_every_section_they_cover(settings: Settings) -> None:
    corpus = load_effective_corpus(settings.handbook_dir, settings.corpus.as_of)
    windows = chunk_corpus(corpus, 160, 40, "window")
    assert all(WINDOW_ID.match(c.chunk_id) for c in windows)
    assert any(len(c.sections) > 1 for c in windows)
    for chunk in windows:
        assert chunk.evidence_keys == {f"{chunk.doc_id}#{s}" for s in chunk.sections}


def test_only_effective_versions_are_chunked(chunks: list[Chunk]) -> None:
    versions = {(c.doc_id, c.version) for c in chunks}
    assert ("OPS-101", "2.1") not in versions
    assert ("HR-201", "3.2") not in versions
    assert ("HR-202", "3.0") not in versions
    # 40p per mile appears only in the superseded expenses policy.
    assert not any("40p per mile" in c.text for c in chunks)


def test_table_rows_are_never_split(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        for line in chunk.text.splitlines():
            if line.startswith("|"):
                assert line.rstrip().endswith("|"), chunk.chunk_id


def test_search_text_includes_headings(chunks: list[Chunk]) -> None:
    mileage = next(c for c in chunks if c.chunk_id == "HR-201:v4.0:s4:c1")
    assert mileage.search_text.startswith("Expenses Policy > 4. Mileage")


def test_packing_respects_size_and_carries_overlap() -> None:
    # Three bullet points of 30 words each ("-" counts as a word).
    body = "\n".join("- " + " ".join([letter] * 29) for letter in "abc")
    units = split_units(Section("1", "Rules", body), 70, 35)
    assert [u.words for u in units] == [30, 30, 30]
    groups = pack_units(units, 70, 35)
    assert [len(g) for g in groups] == [2, 2]
    # The second chunk starts with the last unit of the first: the overlap.
    assert groups[1][0] == groups[0][-1]


def test_long_paragraph_is_split_into_overlapping_windows() -> None:
    words = [f"w{i}" for i in range(100)]
    units = split_units(Section("1", "Long", " ".join(words)), 40, 10)
    assert [u.words for u in units] == [40, 40, 40]
    assert units[1].text.split()[0] == "w30"
