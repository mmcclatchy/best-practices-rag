from unittest.mock import MagicMock

import pytest
from best_practices_rag.graph_models import EntityNode, Relation

from best_practices_rag.parser import GraphBundle
from best_practices_rag.storage import store_results, _merge_node, _merge_relation


def _make_node(
    name: str = "n1", label: str = "BestPractice", **props: str
) -> EntityNode:
    node = EntityNode(label=label, name=name, properties=props or {})
    return node


def _make_relation(source: str, target: str, label: str = "APPLIES_TO") -> Relation:
    return Relation(source_id=source, target_id=target, label=label)


def _make_graph_store() -> MagicMock:
    gs = MagicMock()
    gs.structured_query.return_value = []
    return gs


def test_store_results_returns_node_count() -> None:
    bundle = GraphBundle(
        nodes=[_make_node("n1"), _make_node("n2")],
        relations=[_make_relation("n1", "n2")],
    )
    gs = _make_graph_store()
    count = store_results(bundle, gs)
    assert count == 2


def test_store_results_calls_structured_query_for_each_node_and_relation() -> None:
    bundle = GraphBundle(
        nodes=[_make_node("n1"), _make_node("n2")],
        relations=[_make_relation("n1", "n2")],
    )
    gs = _make_graph_store()
    store_results(bundle, gs)
    assert gs.structured_query.call_count == 3


def test_merge_node_strips_none_props() -> None:
    node = EntityNode(
        label="BestPractice", name="n1", properties={"title": "T", "body": None}
    )
    gs = _make_graph_store()
    _merge_node(node, gs)
    props = gs.structured_query.call_args[1]["param_map"]["props"]
    assert "body" not in props
    assert props["title"] == "T"


def test_merge_node_passes_correct_cypher_params() -> None:
    node = _make_node("bp:fastapi:async", "BestPractice", title="FastAPI Async")
    gs = _make_graph_store()
    _merge_node(node, gs)
    param_map = gs.structured_query.call_args[1]["param_map"]
    assert param_map["name"] == "bp:fastapi:async"
    assert param_map["label"] == "BestPractice"


def test_merge_relation_applies_to_succeeds() -> None:
    rel = _make_relation("n1", "n2", "APPLIES_TO")
    gs = _make_graph_store()
    _merge_relation(rel, gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "APPLIES_TO" in cypher


def test_merge_relation_version_of_succeeds() -> None:
    rel = _make_relation("n1", "n2", "VERSION_OF")
    gs = _make_graph_store()
    _merge_relation(rel, gs)
    cypher = gs.structured_query.call_args[0][0]
    assert "VERSION_OF" in cypher


def test_merge_relation_rejects_unknown_label() -> None:
    rel = _make_relation("n1", "n2", "INJECTED_LABEL")
    gs = _make_graph_store()
    with pytest.raises(ValueError, match="not allowed"):
        _merge_relation(rel, gs)
    gs.structured_query.assert_not_called()


def test_store_results_empty_bundle() -> None:
    bundle = GraphBundle(nodes=[], relations=[])
    gs = _make_graph_store()
    count = store_results(bundle, gs)
    assert count == 0
    gs.structured_query.assert_not_called()
