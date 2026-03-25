import logging

from best_practices_rag.graph_models import EntityNode, Relation
from best_practices_rag.graph_store import GraphStore
from best_practices_rag.parser import GraphBundle


logger = logging.getLogger(__name__)

_ALLOWED_RELATION_LABELS = frozenset({"APPLIES_TO", "VERSION_OF"})


def store_results(bundle: GraphBundle, graph_store: GraphStore) -> int:
    """Merge all nodes and relations from bundle into Neo4j using UNWIND batches."""
    logger.info(
        "Storage started — %d nodes, %d relations",
        len(bundle.nodes),
        len(bundle.relations),
    )
    _batch_merge_nodes(bundle.nodes, graph_store)
    _batch_merge_relations(bundle.relations, graph_store)
    total_ops = len(bundle.nodes) + len(bundle.relations)
    logger.info("Storage complete — %d merge operations", total_ops)
    return len(bundle.nodes)


def _batch_merge_nodes(nodes: list[EntityNode], graph_store: GraphStore) -> None:
    if not nodes:
        return
    rows = [
        {
            "name": node.name,
            "label": node.label,
            "props": {k: v for k, v in (node.properties or {}).items() if v is not None},
        }
        for node in nodes
    ]
    graph_store.structured_query(
        "UNWIND $rows AS row MERGE (n:__Entity__ {name: row.name}) SET n.label = row.label, n += row.props",
        param_map={"rows": rows},
    )


def _batch_merge_relations(relations: list[Relation], graph_store: GraphStore) -> None:
    if not relations:
        return
    # Validate all labels before executing any query (fail-fast)
    for rel in relations:
        if rel.label not in _ALLOWED_RELATION_LABELS:
            logger.warning("Relation label %r rejected — not in allowlist", rel.label)
            raise ValueError(
                f"Relation label {rel.label!r} is not allowed. "
                f"Permitted labels: {sorted(_ALLOWED_RELATION_LABELS)}"
            )
    # Group by label, one UNWIND query per label
    by_label: dict[str, list[dict[str, str]]] = {}
    for rel in relations:
        by_label.setdefault(rel.label, []).append(
            {"source_id": rel.source_id, "target_id": rel.target_id}
        )
    for label, rows in by_label.items():
        cypher = (
            f"UNWIND $rows AS row"
            f" MATCH (s:__Entity__ {{name: row.source_id}})"
            f" MATCH (t:__Entity__ {{name: row.target_id}})"
            f" MERGE (s)-[r:{label}]->(t)"
        )
        graph_store.structured_query(cypher, param_map={"rows": rows})
