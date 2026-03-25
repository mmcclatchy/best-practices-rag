from typing import Any

import pytest
from pytest_mock import MockerFixture

from best_practices_rag.graph_models import EntityNode, Relation
from best_practices_rag.graph_store import GraphStore
from best_practices_rag.parser import GraphBundle
from best_practices_rag.storage import (
    _batch_merge_nodes,
    _batch_merge_relations,
    store_results,
)


def _make_node(
    name: str = "n1", label: str = "BestPractice", **props: str
) -> EntityNode:
    node = EntityNode(label=label, name=name, properties=props or {})
    return node


def _make_relation(source: str, target: str, label: str = "APPLIES_TO") -> Relation:
    return Relation(source_id=source, target_id=target, label=label)


def _make_graph_store(mocker: MockerFixture) -> Any:
    gs = mocker.MagicMock()
    gs.structured_query.return_value = []
    return gs


def test_store_results_returns_node_count(mocker: MockerFixture) -> None:
    bundle = GraphBundle(
        nodes=[_make_node("n1"), _make_node("n2")],
        relations=[_make_relation("n1", "n2")],
    )
    gs = _make_graph_store(mocker)
    count = store_results(bundle, gs)
    assert count == 2


def test_store_results_calls_structured_query_for_each_node_and_relation(
    mocker: MockerFixture,
) -> None:
    bundle = GraphBundle(
        nodes=[_make_node("n1"), _make_node("n2")],
        relations=[_make_relation("n1", "n2")],
    )
    gs = _make_graph_store(mocker)
    store_results(bundle, gs)
    assert gs.structured_query.call_count <= 3


def test_batch_merge_nodes_strips_none_props(mocker: MockerFixture) -> None:
    node = EntityNode(
        label="BestPractice", name="n1", properties={"title": "T", "body": None}
    )
    gs = _make_graph_store(mocker)
    _batch_merge_nodes([node], gs)
    call_kwargs = gs.structured_query.call_args[1]
    rows = call_kwargs["param_map"]["rows"]
    assert len(rows) == 1
    assert "body" not in rows[0]["props"]
    assert rows[0]["props"]["title"] == "T"


def test_batch_merge_nodes_passes_correct_cypher_params(mocker: MockerFixture) -> None:
    node = _make_node("bp:fastapi:async", "BestPractice", title="FastAPI Async")
    gs = _make_graph_store(mocker)
    _batch_merge_nodes([node], gs)
    call_kwargs = gs.structured_query.call_args[1]
    rows = call_kwargs["param_map"]["rows"]
    assert rows[0]["name"] == "bp:fastapi:async"
    assert rows[0]["label"] == "BestPractice"


def test_batch_merge_nodes_uses_unwind_cypher(mocker: MockerFixture) -> None:
    node = _make_node("n1")
    gs = _make_graph_store(mocker)
    _batch_merge_nodes([node], gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "UNWIND" in cypher


def test_batch_merge_nodes_skips_call_when_empty(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker)
    _batch_merge_nodes([], gs)
    gs.structured_query.assert_not_called()


def test_batch_merge_relations_applies_to_succeeds(mocker: MockerFixture) -> None:
    rel = _make_relation("n1", "n2", "APPLIES_TO")
    gs = _make_graph_store(mocker)
    _batch_merge_relations([rel], gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "APPLIES_TO" in cypher


def test_batch_merge_relations_version_of_succeeds(mocker: MockerFixture) -> None:
    rel = _make_relation("n1", "n2", "VERSION_OF")
    gs = _make_graph_store(mocker)
    _batch_merge_relations([rel], gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "VERSION_OF" in cypher


def test_batch_merge_relations_rejects_unknown_label(mocker: MockerFixture) -> None:
    rel = _make_relation("n1", "n2", "INJECTED_LABEL")
    gs = _make_graph_store(mocker)
    with pytest.raises(ValueError, match="not allowed"):
        _batch_merge_relations([rel], gs)
    gs.structured_query.assert_not_called()


def test_batch_merge_relations_uses_unwind_cypher(mocker: MockerFixture) -> None:
    rel = _make_relation("n1", "n2", "APPLIES_TO")
    gs = _make_graph_store(mocker)
    _batch_merge_relations([rel], gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "UNWIND" in cypher


def test_batch_merge_relations_skips_empty_labels(mocker: MockerFixture) -> None:
    # Two relations with the same label: only 1 query should fire
    rels = [
        _make_relation("n1", "n2", "APPLIES_TO"),
        _make_relation("n2", "n3", "APPLIES_TO"),
    ]
    gs = _make_graph_store(mocker)
    _batch_merge_relations(rels, gs)
    assert gs.structured_query.call_count == 1


def test_batch_merge_relations_rejects_unknown_label_before_any_query(
    mocker: MockerFixture,
) -> None:
    # Mix of valid and invalid labels; structured_query must not be called at all
    rels = [
        _make_relation("n1", "n2", "APPLIES_TO"),
        _make_relation("n2", "n3", "INJECTED_LABEL"),
    ]
    gs = _make_graph_store(mocker)
    with pytest.raises(ValueError, match="not allowed"):
        _batch_merge_relations(rels, gs)
    gs.structured_query.assert_not_called()


def test_batch_merge_relations_skips_call_when_empty(mocker: MockerFixture) -> None:
    gs = _make_graph_store(mocker)
    _batch_merge_relations([], gs)
    gs.structured_query.assert_not_called()


def test_store_results_empty_bundle(mocker: MockerFixture) -> None:
    bundle = GraphBundle(nodes=[], relations=[])
    gs = _make_graph_store(mocker)
    count = store_results(bundle, gs)
    assert count == 0
    gs.structured_query.assert_not_called()


def test_graph_store_context_manager_calls_close_on_exit(mocker: MockerFixture) -> None:
    mocker.patch("best_practices_rag.graph_store.GraphDatabase")
    gs = GraphStore(uri="bolt://localhost:7687", username="neo4j", password="pass")
    mock_close = mocker.patch.object(gs, "close")
    with gs:
        pass
    mock_close.assert_called_once()


def test_graph_store_context_manager_calls_close_on_exception(
    mocker: MockerFixture,
) -> None:
    mocker.patch("best_practices_rag.graph_store.GraphDatabase")
    gs = GraphStore(uri="bolt://localhost:7687", username="neo4j", password="pass")
    mock_close = mocker.patch.object(gs, "close")
    with pytest.raises(RuntimeError):
        with gs:
            raise RuntimeError("test error")
    mock_close.assert_called_once()
