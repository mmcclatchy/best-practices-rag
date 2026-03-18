import pytest
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from best_practices_rag.knowledge_base import (
    query_knowledge_base,
    summarize_neo4j_results,
)


def _make_graph_store(mocker: MockerFixture, rows: list[dict]) -> MagicMock:
    gs = mocker.MagicMock()
    gs.structured_query.return_value = rows
    return gs


def test_returns_empty_when_no_results(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [])
    result = query_knowledge_base("query", gs, tech_names=["fastapi"])
    assert result == []


def test_tech_and_topics_uses_topic_filtered_cypher(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, tech_names=["fastapi"], topic_keywords=["async"])
    cypher = gs.structured_query.call_args[0][0]
    assert "db.index.fulltext.queryNodes" in cypher


def test_tech_only_uses_known_cypher(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, tech_names=["fastapi"])
    cypher = gs.structured_query.call_args[0][0]
    assert "match_count" in cypher
    assert "fulltext" not in cypher


def test_topic_only_uses_topic_only_cypher(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, topic_keywords=["async"])
    cypher = gs.structured_query.call_args[0][0]
    assert "db.index.fulltext.queryNodes" in cypher
    assert "tech_names" not in gs.structured_query.call_args[1]["param_map"]
    assert "fulltext_query" in gs.structured_query.call_args[1]["param_map"]


def test_fallback_cypher_when_no_tech_or_topics(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "BestPractice" in cypher
    assert "tech_names" not in gs.structured_query.call_args[1]["param_map"]


def test_lang_filter_injected_into_cypher(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [])
    query_knowledge_base("q", gs, tech_names=["fastapi"], lang_names=["python"])
    cypher = gs.structured_query.call_args[0][0]
    assert "lang_names" in cypher


def test_row_parsed_with_version_and_display_name(mocker: MockerFixture) -> None:
    rows = [
        {
            "bp.name": "n1",
            "bp.title": "T",
            "bp.body": "B",
            "version": "0.116",
            "display_name": "FastAPI",
        }
    ]
    gs = _make_graph_store(mocker, rows)
    result = query_knowledge_base("q", gs, tech_names=["fastapi"])
    assert result[0]["version"] == "0.116"
    assert result[0]["display_name"] == "FastAPI"


def test_row_parsed_without_version(mocker: MockerFixture) -> None:
    rows = [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}]
    gs = _make_graph_store(mocker, rows)
    result = query_knowledge_base("q", gs)
    assert "version" not in result[0]


def test_summarize_empty_returns_no_results_message() -> None:
    assert (
        summarize_neo4j_results([])
        == "No existing best practices found in the knowledge base."
    )


def test_summarize_deduplicates_by_name() -> None:
    rows = [
        {"name": "bp1", "title": "T", "body": "B"},
        {"name": "bp1", "title": "T", "body": "B"},
    ]
    summary = summarize_neo4j_results(rows)
    assert summary.count("T") == 1


def test_summarize_includes_tech_header_when_display_name_present() -> None:
    rows = [
        {
            "name": "bp1",
            "title": "My Title",
            "body": "Body",
            "display_name": "FastAPI",
            "version": "0.116",
        }
    ]
    summary = summarize_neo4j_results(rows)
    assert "FastAPI" in summary
    assert "0.116" in summary


def test_summarize_truncates_long_body() -> None:
    rows = [{"name": "bp1", "title": "T", "body": "x" * 2000}]
    summary = summarize_neo4j_results(rows, truncate=True)
    assert "..." in summary


def test_row_parsed_includes_tech_versions_at_synthesis(mocker: MockerFixture) -> None:
    rows = [
        {
            "bp.name": "n1",
            "bp.title": "T",
            "bp.body": "B",
            "bp.tech_versions_at_synthesis": '{"fastapi":"0.116"}',
            "bp.synthesized_at": "2025-01-01T00:00:00+00:00",
        }
    ]
    gs = _make_graph_store(mocker, rows)
    result = query_knowledge_base("q", gs)
    assert result[0]["tech_versions_at_synthesis"] == '{"fastapi":"0.116"}'
    assert result[0]["synthesized_at"] == "2025-01-01T00:00:00+00:00"


def test_row_parsed_tech_versions_defaults_to_empty_string(
    mocker: MockerFixture,
) -> None:
    rows = [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}]
    gs = _make_graph_store(mocker, rows)
    result = query_knowledge_base("q", gs)
    assert result[0]["tech_versions_at_synthesis"] == ""
    assert result[0]["synthesized_at"] == ""


def test_summarize_no_truncation_when_disabled() -> None:
    rows = [{"name": "bp1", "title": "T", "body": "x" * 2000}]
    summary = summarize_neo4j_results(rows, truncate=False)
    assert "x" * 2000 in summary


# Fulltext-specific tests (replacing hybrid RRF tests)


def test_topic_only_uses_fulltext_not_contains(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, topic_keywords=["async"])
    cypher = gs.structured_query.call_args[0][0]
    assert "CONTAINS" not in cypher


def test_topic_filtered_uses_fulltext_not_contains(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, tech_names=["fastapi"], topic_keywords=["async"])
    cypher = gs.structured_query.call_args[0][0]
    assert "CONTAINS" not in cypher


def test_topic_only_passes_fulltext_query_param(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, topic_keywords=["async"])
    param_map = gs.structured_query.call_args[1]["param_map"]
    assert "fulltext_query" in param_map


def test_topic_filtered_passes_fulltext_and_tech_params(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [{"bp.name": "n1", "bp.title": "T", "bp.body": "B"}])
    query_knowledge_base("q", gs, tech_names=["fastapi"], topic_keywords=["async"])
    param_map = gs.structured_query.call_args[1]["param_map"]
    assert "fulltext_query" in param_map
    assert "tech_names" in param_map


def test_query_knowledge_base_rejects_query_embedding(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [])
    with pytest.raises(TypeError):
        query_knowledge_base("q", gs, query_embedding=[0.1] * 384)  # type: ignore[call-arg]


def test_lang_filter_with_topic_only_fulltext(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [])
    query_knowledge_base("q", gs, topic_keywords=["async"], lang_names=["python"])
    cypher = gs.structured_query.call_args[0][0]
    assert "lang_names" in cypher


def test_lang_filter_with_topic_filtered_fulltext(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker, [])
    query_knowledge_base(
        "q", gs, tech_names=["fastapi"], topic_keywords=["async"], lang_names=["python"]
    )
    cypher = gs.structured_query.call_args[0][0]
    assert "lang_names" in cypher
