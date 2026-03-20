from pathlib import Path

from best_practices_rag.staleness import check_staleness, load_current_versions, load_tech_info


def test_load_current_versions_parses_markdown_table(tmp_path: Path) -> None:
    table = (
        "# Tech Versions\n\n"
        "| Technology | Version | Release Date | Key Changes |\n"
        "| --- | --- | --- | --- |\n"
        "| FastAPI | 0.116 | 2025-01-01 | Some changes |\n"
        "| Neo4j | 5.28 | 2025-01-01 | Other changes |\n"
    )
    (tmp_path / "tech-versions.md").write_text(table, encoding="utf-8")
    versions = load_current_versions(tmp_path)
    assert versions["fastapi"] == "0.116"
    assert versions["neo4j"] == "5.28"


def test_load_tech_info_parses_three_columns(tmp_path: Path) -> None:
    table = (
        "# Tech Versions\n\n"
        "| Technology | Version | Release Date | Key Changes |\n"
        "| --- | --- | --- | --- |\n"
        "| FastAPI | 0.116 | 2025-01-01 | Some changes |\n"
        "| SQLAlchemy | 2.0 | 2023-01-26 | Other changes |\n"
    )
    (tmp_path / "tech-versions.md").write_text(table, encoding="utf-8")
    info = load_tech_info(tmp_path)
    assert info["fastapi"]["version"] == "0.116"
    assert info["fastapi"]["release_date"] == "2025-01-01"
    assert info["sqlalchemy"]["release_date"] == "2023-01-26"


def test_check_staleness_empty_string_is_stale() -> None:
    result = {"tech_versions_at_synthesis": ""}
    current = {"fastapi": "0.116"}
    info = check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "no_version_info"


def test_check_staleness_matching_versions_not_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"fastapi": "0.116"}'}
    current = {"fastapi": "0.116"}
    info = check_staleness(result, current)
    assert info["is_stale"] is False
    assert info["reason"] is None
    assert "fastapi" in info["fresh_technologies"]


def test_check_staleness_mismatched_version_is_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"fastapi": "0.115"}'}
    current = {"fastapi": "0.116"}
    info = check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "version_mismatch"
    assert "fastapi" in info["stale_technologies"]


def test_check_staleness_malformed_json_is_stale() -> None:
    result = {"tech_versions_at_synthesis": "not-json"}
    current = {"fastapi": "0.116"}
    info = check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "no_version_info"


def test_check_staleness_tech_not_in_table_is_fresh() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "1.26"}'}
    current: dict[str, str] = {}
    info = check_staleness(result, current)
    assert info["is_stale"] is False
    assert "beanie" in info["fresh_technologies"]
    assert "beanie" not in info["stale_technologies"]


def test_check_staleness_stored_latest_tech_absent_is_fresh() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "latest"}'}
    current: dict[str, str] = {}
    info = check_staleness(result, current)
    assert info["is_stale"] is False
    assert "beanie" in info["fresh_technologies"]


def test_check_staleness_stored_latest_tech_present_is_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "latest"}'}
    current = {"beanie": "2.0"}
    info = check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "version_mismatch"
    assert "beanie" in info["stale_technologies"]
    assert info["version_deltas"]["beanie"]["stored"] == "latest"
    assert info["version_deltas"]["beanie"]["current"] == "2.0"
