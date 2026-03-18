import logging

from llama_index.core.graph_stores.types import EntityNode, Relation
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from best_practices_rag.parser import GraphBundle


logger = logging.getLogger(__name__)


def store_results(bundle: GraphBundle, graph_store: Neo4jPropertyGraphStore) -> int:
    """Merge all nodes and relations from bundle into Neo4j.

    POC_NOTE: Nodes and relations are merged one at a time (N individual round-trips).
    Shortcut rationale: Simplicity and debuggability outweigh throughput at POC
      stage; typical bundles are <30 nodes.
    Production approach: Replace the loops with a single batched Cypher using
      UNWIND over a list parameter:
        UNWIND $rows AS row
        MERGE (n:__Entity__ {name: row.name})
        SET n.label = row.label, n += row.props
      This reduces round-trips to 2 (one for nodes, one for relations) regardless
      of bundle size.
    """
    logger.info(
        "Storage started — %d nodes, %d relations",
        len(bundle.nodes),
        len(bundle.relations),
    )
    for node in bundle.nodes:
        logger.debug("  merging node — label=%r name=%r", node.label, node.name)
        _merge_node(node, graph_store)
    for rel in bundle.relations:
        logger.debug(
            "  merging relation — %r -[%s]-> %r",
            rel.source_id,
            rel.label,
            rel.target_id,
        )
        _merge_relation(rel, graph_store)
    total_ops = len(bundle.nodes) + len(bundle.relations)
    logger.info("Storage complete — %d merge operations", total_ops)
    return len(bundle.nodes)


def _merge_node(node: EntityNode, graph_store: Neo4jPropertyGraphStore) -> None:
    props = {k: v for k, v in (node.properties or {}).items() if v is not None}
    graph_store.structured_query(
        "MERGE (n:__Entity__ {name: $name}) SET n.label = $label, n += $props",
        param_map={"name": node.name, "label": node.label, "props": props},
    )


_ALLOWED_RELATION_LABELS = frozenset({"APPLIES_TO", "VERSION_OF"})


def _merge_relation(rel: Relation, graph_store: Neo4jPropertyGraphStore) -> None:
    # Guard against Cypher injection via rel.label — only whitelisted labels are
    # permitted because relationship type names cannot be parameterized in Cypher.
    if rel.label not in _ALLOWED_RELATION_LABELS:
        logger.warning("Relation label %r rejected — not in allowlist", rel.label)
        raise ValueError(
            f"Relation label {rel.label!r} is not allowed. "
            f"Permitted labels: {sorted(_ALLOWED_RELATION_LABELS)}"
        )
    cypher = (
        f"MATCH (s:__Entity__ {{name: $source_id}})"
        f" MATCH (t:__Entity__ {{name: $target_id}})"
        f" MERGE (s)-[r:{rel.label}]->(t)"
    )
    graph_store.structured_query(
        cypher,
        param_map={"source_id": rel.source_id, "target_id": rel.target_id},
    )
