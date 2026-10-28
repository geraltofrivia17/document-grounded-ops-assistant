"""Load handbook documents and decide which version of each is in force.

Effective-document rule, applied per doc_id on the as-of date:

1. Versions marked ``superseded`` are never used.
2. Versions whose effective date is after the as-of date are not used yet.
3. Of the remaining ``active`` versions, the one with the latest effective date is used.
   It replaces any older active version, even if the older file was never re-marked.
4. Two remaining active versions with the same effective date are an error, because
   there is no safe way to choose between them.

Only effective versions are chunked and indexed, so a superseded rule cannot reach
the model or appear in a citation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

FRONT_MATTER_DELIMITER = "+++"
DOCUMENT_GLOB = "*_v*.md"


class CorpusError(ValueError):
    """The handbook cannot be loaded safely."""


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(pattern=r"^[A-Z]{2,4}-\d{3}$")
    title: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+$")
    effective_date: dt.date
    status: Literal["active", "superseded"]
    owner: str
    source: Literal["internal", "external"]
    supersedes: str | None = None


@dataclass(frozen=True)
class Document:
    metadata: DocumentMetadata
    body: str
    path: Path

    @property
    def doc_id(self) -> str:
        return self.metadata.doc_id

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def key(self) -> str:
        return f"{self.doc_id} v{self.version}"


@dataclass(frozen=True)
class Exclusion:
    doc_id: str
    version: str
    reason: str


@dataclass(frozen=True)
class EffectiveCorpus:
    as_of: dt.date
    documents: tuple[Document, ...]
    exclusions: tuple[Exclusion, ...]

    def fingerprint(self) -> str:
        """Hash of the effective text, recorded with every evaluation run."""
        digest = hashlib.sha256()
        for document in self.documents:
            digest.update(document.key.encode())
            digest.update(document.body.encode())
        return digest.hexdigest()[:16]


def parse_document(path: Path) -> Document:
    """Split TOML front matter from the Markdown body and validate the metadata."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise CorpusError(f"{path.name}: missing '+++' front matter")
    try:
        end = lines.index(FRONT_MATTER_DELIMITER, 1)
    except ValueError as error:
        raise CorpusError(f"{path.name}: front matter is not closed with '+++'") from error
    try:
        raw = tomllib.loads("\n".join(lines[1:end]))
        metadata = DocumentMetadata.model_validate(raw)
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise CorpusError(f"{path.name}: invalid front matter: {error}") from error
    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise CorpusError(f"{path.name}: document body is empty")
    return Document(metadata=metadata, body=body, path=path)


def load_documents(handbook_dir: Path) -> list[Document]:
    paths = sorted(handbook_dir.glob(DOCUMENT_GLOB))
    if not paths:
        raise CorpusError(f"No documents matching {DOCUMENT_GLOB} in {handbook_dir}")
    documents = [parse_document(path) for path in paths]
    seen: set[str] = set()
    for document in documents:
        if document.key in seen:
            raise CorpusError(f"Duplicate document version: {document.key}")
        seen.add(document.key)
    return documents


def select_effective(documents: list[Document], as_of: dt.date) -> EffectiveCorpus:
    """Apply the effective-document rule described in the module docstring."""
    by_id: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        by_id[document.doc_id].append(document)

    chosen: list[Document] = []
    exclusions: list[Exclusion] = []
    for doc_id in sorted(by_id):
        candidates = []
        for document in by_id[doc_id]:
            meta = document.metadata
            if meta.status == "superseded":
                exclusions.append(Exclusion(doc_id, meta.version, "marked superseded"))
            elif meta.effective_date > as_of:
                reason = f"not yet effective (takes effect {meta.effective_date.isoformat()})"
                exclusions.append(Exclusion(doc_id, meta.version, reason))
            else:
                candidates.append(document)
        if not candidates:
            logger.warning("No effective version of %s on %s", doc_id, as_of)
            continue
        candidates.sort(key=lambda d: d.metadata.effective_date, reverse=True)
        latest = candidates[0]
        if (
            len(candidates) > 1
            and candidates[1].metadata.effective_date == latest.metadata.effective_date
        ):
            raise CorpusError(
                f"{doc_id}: versions {latest.version} and {candidates[1].version} "
                "are both active from the same date"
            )
        chosen.append(latest)
        for older in candidates[1:]:
            reason = (
                f"replaced by v{latest.version} from {latest.metadata.effective_date.isoformat()}"
            )
            exclusions.append(Exclusion(doc_id, older.version, reason))

    for exclusion in exclusions:
        logger.info("Excluded %s v%s: %s", exclusion.doc_id, exclusion.version, exclusion.reason)
    return EffectiveCorpus(as_of=as_of, documents=tuple(chosen), exclusions=tuple(exclusions))


def load_effective_corpus(handbook_dir: Path, as_of: dt.date) -> EffectiveCorpus:
    return select_effective(load_documents(handbook_dir), as_of)
