from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from best_practices_rag.config import Settings
import best_practices_rag.config as config_module


def test_inference_fields_absent() -> None:
    assert not hasattr(Settings.model_fields, "inference_api_key")
    assert "inference_api_key" not in Settings.model_fields
    assert "inference_base_url" not in Settings.model_fields
    assert "inference_extract_model" not in Settings.model_fields
    assert "inference_gap_model" not in Settings.model_fields
    assert "inference_synthesis_model" not in Settings.model_fields


def test_exa_filter_fields_present() -> None:
    assert "exa_include_domains" not in Settings.model_fields
    assert "exa_exclude_domains" in Settings.model_fields
    assert "exa_min_published_year_offset" in Settings.model_fields


def test_exa_exclude_domains_default() -> None:
    with patch.dict(
        "os.environ",
        {
            "NEO4J_PASSWORD": "test",
            "EXA_API_KEY": "test",
        },
        clear=True,
    ):
        s = Settings()  # type: ignore[call-arg]
        assert isinstance(s.exa_exclude_domains, list)
        assert "w3schools.com" in s.exa_exclude_domains
        assert "geeksforgeeks.org" in s.exa_exclude_domains
        assert "tutorialspoint.com" in s.exa_exclude_domains
        assert "medium.com" in s.exa_exclude_domains


def test_exa_min_published_year_offset_default() -> None:
    with patch.dict(
        "os.environ",
        {
            "NEO4J_PASSWORD": "test",
            "EXA_API_KEY": "test",
        },
        clear=True,
    ):
        s = Settings()  # type: ignore[call-arg]
        assert s.exa_min_published_year_offset == 2


def test_get_settings_singleton() -> None:
    config_module._settings = None
    with patch.dict(
        "os.environ",
        {
            "NEO4J_PASSWORD": "test",
            "EXA_API_KEY": "test",
        },
        clear=True,
    ):
        s1 = config_module.get_settings()
        s2 = config_module.get_settings()
        assert s1 is s2


def test_preserved_fields_present() -> None:
    assert "neo4j_uri" in Settings.model_fields
    assert "neo4j_username" in Settings.model_fields
    assert "neo4j_password" in Settings.model_fields
    assert "exa_api_key" in Settings.model_fields
    assert "exa_content_top_n" in Settings.model_fields


def test_neo4j_username_default() -> None:
    with patch.dict(
        "os.environ",
        {
            "NEO4J_PASSWORD": "test",
            "EXA_API_KEY": "test",
        },
        clear=True,
    ):
        s = Settings(_env_file=None, _secrets_dir=None)  # type: ignore[call-arg]
        assert s.neo4j_username == "neo4j"


def test_exa_api_key_required(tmp_path: Path) -> None:
    with patch.dict(
        "os.environ",
        {
            "NEO4J_PASSWORD": "test",
        },
        clear=True,
    ):
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, _secrets_dir=str(tmp_path / "empty"))  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("exa_api_key",) for e in errors)


def test_secrets_dir_in_model_config() -> None:
    assert "secrets_dir" in Settings.model_config
