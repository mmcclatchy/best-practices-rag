import sys
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


# Allow importing module-level functions from the script directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

_PROJECT_ROOT = Path(__file__).parent.parent

# Try .claude/ path first (dev repo), fall back to package data (release repo)
_SCRIPT_CANDIDATES = [
    _PROJECT_ROOT / ".claude/skills/best-practices-rag/scripts/query_kb.py",
    _PROJECT_ROOT / "best_practices_rag/_claude_files/skills/best-practices-rag/scripts/query_kb.py",
]
_SCRIPT_PATH = next((p for p in _SCRIPT_CANDIDATES if p.exists()), None)
assert _SCRIPT_PATH is not None, "query_kb.py not found in any expected location"

_spec = spec_from_file_location("query_kb_module", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_query_kb_module = module_from_spec(_spec)
_spec.loader.exec_module(_query_kb_module)

_load_current_versions = _query_kb_module._load_current_versions
_check_staleness = _query_kb_module._check_staleness


def test_load_current_versions_parses_markdown_table(tmp_path: Path) -> None:
    table = (
        "# Tech Versions\n\n"
        "| Technology | Version | Release Date | Key Changes |\n"
        "| --- | --- | --- | --- |\n"
        "| FastAPI | 0.116 | 2025-01-01 | Some changes |\n"
        "| Neo4j | 5.28 | 2025-01-01 | Other changes |\n"
    )
    (tmp_path / "tech-versions.md").write_text(table, encoding="utf-8")
    versions = _load_current_versions(tmp_path)
    assert versions["fastapi"] == "0.116"
    assert versions["neo4j"] == "5.28"


def test_check_staleness_empty_string_is_stale() -> None:
    result = {"tech_versions_at_synthesis": ""}
    current = {"fastapi": "0.116"}
    info = _check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "no_version_info"


def test_check_staleness_matching_versions_not_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"fastapi": "0.116"}'}
    current = {"fastapi": "0.116"}
    info = _check_staleness(result, current)
    assert info["is_stale"] is False
    assert info["reason"] is None
    assert "fastapi" in info["fresh_technologies"]


def test_check_staleness_mismatched_version_is_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"fastapi": "0.115"}'}
    current = {"fastapi": "0.116"}
    info = _check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "version_mismatch"
    assert "fastapi" in info["stale_technologies"]


def test_check_staleness_malformed_json_is_stale() -> None:
    result = {"tech_versions_at_synthesis": "not-json"}
    current = {"fastapi": "0.116"}
    info = _check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "no_version_info"


def test_check_staleness_tech_not_in_table_is_fresh() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "1.26"}'}
    current: dict[str, str] = {}
    info = _check_staleness(result, current)
    assert info["is_stale"] is False
    assert "beanie" in info["fresh_technologies"]
    assert "beanie" not in info["stale_technologies"]


def test_check_staleness_stored_latest_tech_absent_is_fresh() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "latest"}'}
    current: dict[str, str] = {}
    info = _check_staleness(result, current)
    assert info["is_stale"] is False
    assert "beanie" in info["fresh_technologies"]


def test_check_staleness_stored_latest_tech_present_is_stale() -> None:
    result = {"tech_versions_at_synthesis": '{"beanie": "latest"}'}
    current = {"beanie": "2.0"}
    info = _check_staleness(result, current)
    assert info["is_stale"] is True
    assert info["reason"] == "version_mismatch"
    assert "beanie" in info["stale_technologies"]
    assert info["version_deltas"]["beanie"]["stored"] == "latest"
    assert info["version_deltas"]["beanie"]["current"] == "2.0"
