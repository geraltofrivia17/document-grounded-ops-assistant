from pathlib import Path

import pytest
from pydantic import ValidationError

from ops_assistant.config import DEFAULT_SETTINGS_PATH, load_settings


def test_default_settings_load() -> None:
    settings = load_settings(environ={})
    assert settings.retrieval.mode in ("keyword", "embedding", "hybrid")
    assert settings.handbook_dir.is_dir()
    assert settings.generation.model in settings.pricing.models


def test_environment_overrides_selected_fields() -> None:
    settings = load_settings(environ={"OPS_PROVIDER": "mock", "OPS_RETRIEVAL_MODE": "hybrid"})
    assert settings.generation.provider == "mock"
    assert settings.retrieval.mode == "hybrid"


def test_invalid_override_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load_settings(environ={"OPS_RETRIEVAL_MODE": "fuzzy"})


def _write_variant(tmp_path: Path, old: str, new: str) -> Path:
    text = DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8")
    assert old in text
    config = tmp_path / "config"
    config.mkdir()
    path = config / "settings.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_misspelt_key_is_an_error(tmp_path: Path) -> None:
    path = _write_variant(tmp_path, "top_k = 5", "topk = 5")
    with pytest.raises(ValidationError):
        load_settings(path, environ={})


def test_overlap_must_be_smaller_than_chunk(tmp_path: Path) -> None:
    path = _write_variant(tmp_path, "overlap_words = 40", "overlap_words = 160")
    with pytest.raises(ValidationError, match="overlap_words"):
        load_settings(path, environ={})


def test_relative_paths_resolve_against_settings_location(tmp_path: Path) -> None:
    path = _write_variant(tmp_path, "top_k = 5", "top_k = 5")
    settings = load_settings(path, environ={})
    assert settings.handbook_dir == tmp_path / "data" / "handbook"
