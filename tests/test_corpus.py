import datetime as dt
from pathlib import Path

import pytest

from ops_assistant.config import Settings
from ops_assistant.corpus import CorpusError, load_documents, parse_document, select_effective

FRONT = """+++
doc_id = "{doc_id}"
title = "Test"
version = "{version}"
effective_date = {date}
status = "{status}"
owner = "Test"
source = "internal"
+++

# Test

## 1. Rule

{body}
"""


def write_doc(
    folder: Path, doc_id="TST-001", version="1.0", date="2026-01-01", status="active", body="Text."
):
    path = folder / f"{doc_id}_v{version}.md"
    path.write_text(
        FRONT.format(doc_id=doc_id, version=version, date=date, status=status, body=body),
        encoding="utf-8",
    )
    return path


def test_handbook_effective_versions(settings: Settings) -> None:
    corpus = select_effective(load_documents(settings.handbook_dir), settings.corpus.as_of)
    chosen = {d.doc_id: d.version for d in corpus.documents}
    assert len(chosen) == 16
    assert chosen["OPS-101"] == "3.0"
    assert chosen["HR-201"] == "4.0"
    assert chosen["HR-202"] == "2.0"
    excluded = {(e.doc_id, e.version): e.reason for e in corpus.exclusions}
    assert excluded[("OPS-101", "2.1")] == "marked superseded"
    assert excluded[("HR-201", "3.2")] == "marked superseded"
    assert excluded[("HR-202", "3.0")].startswith("not yet effective")


def test_future_version_takes_over_on_its_effective_date(settings: Settings) -> None:
    documents = load_documents(settings.handbook_dir)
    corpus = select_effective(documents, dt.date(2027, 1, 1))
    chosen = {d.doc_id: d.version for d in corpus.documents}
    assert chosen["HR-202"] == "3.0"
    reasons = {(e.doc_id, e.version): e.reason for e in corpus.exclusions}
    assert reasons[("HR-202", "2.0")] == "replaced by v3.0 from 2027-01-01"


def test_two_active_versions_from_the_same_date_are_rejected(tmp_path: Path) -> None:
    write_doc(tmp_path, version="1.0")
    write_doc(tmp_path, version="1.1")
    with pytest.raises(CorpusError, match="same date"):
        select_effective(load_documents(tmp_path), dt.date(2026, 6, 1))


def test_document_with_no_effective_version_is_left_out(tmp_path: Path) -> None:
    write_doc(tmp_path, date="2030-01-01")
    corpus = select_effective(load_documents(tmp_path), dt.date(2026, 6, 1))
    assert corpus.documents == ()
    assert corpus.exclusions[0].reason.startswith("not yet effective")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# No front matter\n", "missing"),
        ("+++\ndoc_id = 'TST-001'\n", "not closed"),
        (
            FRONT.format(
                doc_id="bad id", version="1.0", date="2026-01-01", status="active", body="x"
            ),
            "invalid",
        ),
        (
            FRONT.format(
                doc_id="TST-001", version="1.0", date="2026-01-01", status="draft", body="x"
            ),
            "invalid",
        ),
        (
            FRONT.format(
                doc_id="TST-001", version="1.0", date="not-a-date", status="active", body="x"
            ),
            "invalid",
        ),
    ],
)
def test_malformed_documents_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "TST-001_v1.0.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CorpusError, match=message):
        parse_document(path)


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    write_doc(tmp_path, version="1.0")
    (tmp_path / "TST-001_v1.0_copy.md").write_text(
        (tmp_path / "TST-001_v1.0.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(CorpusError, match="Duplicate"):
        load_documents(tmp_path)


def test_fingerprint_changes_when_text_changes(tmp_path: Path) -> None:
    write_doc(tmp_path, body="First.")
    before = select_effective(load_documents(tmp_path), dt.date(2026, 6, 1)).fingerprint()
    write_doc(tmp_path, body="Second.")
    after = select_effective(load_documents(tmp_path), dt.date(2026, 6, 1)).fingerprint()
    assert before != after
