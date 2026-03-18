"""Knowledge base query module.

Provides raw Cypher retrieval from Neo4j via structured_query().
Technology names are provided by the caller (extracted via LLM in the pipeline).

Schema traversal:
  BestPractice -[:APPLIES_TO]-> TechVersion -[:VERSION_OF]-> Technology
"""

import logging
import re

from best_practices_rag.graph_store import GraphStore


logger = logging.getLogger(__name__)


_KNOWN_CYPHER = (
    "MATCH (bp:__Entity__ {label:'BestPractice'})"
    "-[:APPLIES_TO]->(tv:__Entity__ {label:'TechVersion'})"
    "-[:VERSION_OF]->(t:__Entity__ {label:'Technology'})"
    " WHERE t.name IN $tech_names"
    " WITH bp,"
    "  count(DISTINCT t.name) AS match_count,"
    "  collect(DISTINCT tv.version)[0] AS version,"
    "  collect(DISTINCT t.display_name)[0] AS display_name"
    " WHERE match_count >= $min_match"
    " ORDER BY match_count DESC"
    " RETURN bp.name, bp.title, bp.body, bp.tech_versions_at_synthesis, bp.synthesized_at, version, display_name"
    " LIMIT 10"
)

_TOPIC_FILTERED_CYPHER = (
    "CALL db.index.fulltext.queryNodes('bp_fulltext', $fulltext_query)"
    " YIELD node AS bp, score AS ft_score"
    " WHERE bp.label = 'BestPractice'"
    " WITH bp, ft_score"
    " MATCH (bp)-[:APPLIES_TO]->(tv:__Entity__ {label:'TechVersion'})"
    "-[:VERSION_OF]->(t:__Entity__ {label:'Technology'})"
    " WHERE t.name IN $tech_names"
    " WITH bp, ft_score,"
    "  count(DISTINCT t.name) AS match_count,"
    "  collect(DISTINCT tv.version)[0] AS version,"
    "  collect(DISTINCT t.display_name)[0] AS display_name"
    " WHERE match_count >= $min_match"
    " ORDER BY ft_score DESC, match_count DESC"
    " RETURN bp.name, bp.title, bp.body, bp.tech_versions_at_synthesis, bp.synthesized_at, version, display_name"
    " LIMIT 10"
)

_FALLBACK_CYPHER = (
    "MATCH (bp:__Entity__) WHERE bp.label = 'BestPractice'"
    " RETURN bp.name, bp.title, bp.body, bp.tech_versions_at_synthesis, bp.synthesized_at LIMIT 10"
)

_TOPIC_ONLY_CYPHER = (
    "CALL db.index.fulltext.queryNodes('bp_fulltext', $fulltext_query)"
    " YIELD node AS bp, score AS ft_score"
    " WHERE bp.label = 'BestPractice'"
    " ORDER BY ft_score DESC"
    " RETURN bp.name, bp.title, bp.body, bp.tech_versions_at_synthesis, bp.synthesized_at"
    " LIMIT 10"
)


_LANG_FILTER = (
    " AND (bp.languages IS NULL"
    " OR ANY(lang IN $lang_names WHERE toLower(bp.languages) CONTAINS lang))"
)

# Lucene special characters that must be escaped in fulltext queries.
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\])')


def _build_fulltext_query(keywords: list[str]) -> str:
    escaped = [_LUCENE_SPECIAL.sub(r"\\\1", kw) for kw in keywords]
    return " OR ".join(escaped)


def query_knowledge_base(
    query: str,
    graph_store: GraphStore,
    tech_names: list[str] | None = None,
    topic_keywords: list[str] | None = None,
    lang_names: list[str] | None = None,
) -> list[dict]:
    """Query Neo4j for BestPractice nodes matching the given technologies.

    Uses raw Cypher via structured_query(). When topic_keywords are provided,
    uses fulltext index (BM25/Lucene) for retrieval instead of CONTAINS keyword
    matching. Falls back to a broader scan when no technology names are provided.

    Args:
        query: The user query (used for logging context).
        graph_store: Neo4j graph store instance.
        tech_names: Lowercase technology names extracted by LLM. When None
            or empty, falls back to returning all BestPractice nodes.
        topic_keywords: Lowercase topic keywords for relevance scoring.
            When provided alongside tech_names, uses fulltext topic-filtered Cypher.
        lang_names: Optional language filter names.

    Returns a list of dicts with keys: name, title, body, and optionally
    version and display_name when tech-filtered.
    """
    logger.info(
        "Knowledge base query — tech_names=%s topic_keywords=%s lang_names=%s",
        tech_names,
        topic_keywords,
        lang_names,
    )

    use_lang_filter = bool(lang_names)

    if tech_names and topic_keywords:
        min_match = 1 if len(tech_names) <= 1 else 2
        logger.info(
            "Using fulltext topic-filtered Cypher — min_match=%d, keywords=%s",
            min_match,
            topic_keywords,
        )
        cypher = _TOPIC_FILTERED_CYPHER
        if use_lang_filter:
            cypher = cypher.replace(
                " ORDER BY ft_score DESC, match_count",
                _LANG_FILTER + " ORDER BY ft_score DESC, match_count",
            )
        param_map: dict = {
            "tech_names": tech_names,
            "min_match": min_match,
            "fulltext_query": _build_fulltext_query(topic_keywords),
        }
        if use_lang_filter:
            param_map["lang_names"] = lang_names
        raw = graph_store.structured_query(cypher, param_map=param_map)
    elif tech_names:
        min_match = 1 if len(tech_names) <= 1 else 2
        logger.info(
            "Using primary Cypher (tech-filtered, version-aware) — min_match=%d",
            min_match,
        )
        logger.debug("Primary Cypher — tech_names param: %s", tech_names)
        cypher = _KNOWN_CYPHER
        if use_lang_filter:
            cypher = cypher.replace(
                " ORDER BY match_count", _LANG_FILTER + " ORDER BY match_count"
            )
        param_map = {"tech_names": tech_names, "min_match": min_match}
        if use_lang_filter:
            param_map["lang_names"] = lang_names
        logger.debug("Cypher: %s", cypher)
        raw = graph_store.structured_query(cypher, param_map=param_map)
    elif topic_keywords:
        logger.info(
            "Using fulltext topic-only Cypher — keywords=%s",
            topic_keywords,
        )
        cypher = _TOPIC_ONLY_CYPHER
        if use_lang_filter:
            cypher = cypher.replace(
                " ORDER BY ft_score", _LANG_FILTER + " ORDER BY ft_score"
            )
        param_map = {"fulltext_query": _build_fulltext_query(topic_keywords)}
        if use_lang_filter:
            param_map["lang_names"] = lang_names
        raw = graph_store.structured_query(cypher, param_map=param_map)
    else:
        logger.info("Using fallback Cypher (no tech names provided)")
        cypher = _FALLBACK_CYPHER
        if use_lang_filter:
            cypher = cypher.replace(" RETURN", _LANG_FILTER + " RETURN")
        param_map = {}
        if use_lang_filter:
            param_map["lang_names"] = lang_names
        logger.debug("Cypher: %s", cypher)
        raw = graph_store.structured_query(cypher, param_map=param_map)

    if not raw:
        logger.info("Knowledge base returned 0 results")
        return []

    logger.info("Knowledge base returned %d results", len(raw))
    logger.debug("Raw Neo4j rows: %s", raw)

    # Primary query returns bp.* + tv.version + t.display_name;
    # fallback returns only bp.* fields.
    results = []
    for row in raw:
        entry: dict = {
            "name": row.get("bp.name", row.get("n.name", "")),
            "title": row.get("bp.title", row.get("n.title", "")),
            "body": row.get("bp.body", row.get("n.body", "")),
        }
        if "version" in row:
            entry["version"] = row["version"]
        elif "tv.version" in row:
            entry["version"] = row["tv.version"]
        if "display_name" in row:
            entry["display_name"] = row["display_name"]
        elif "t.display_name" in row:
            entry["display_name"] = row["t.display_name"]
        entry["tech_versions_at_synthesis"] = row.get(
            "bp.tech_versions_at_synthesis", ""
        )
        entry["synthesized_at"] = row.get("bp.synthesized_at", "")
        logger.debug(
            "Row parsed — name=%r title=%r version=%r display_name=%r body_length=%d",
            entry.get("name"),
            entry.get("title"),
            entry.get("version"),
            entry.get("display_name"),
            len(entry.get("body", "")),
        )
        results.append(entry)

    return results


_MAX_BODY_CHARS: int = 800
_MAX_TOTAL_CHARS: int = 40_000


def summarize_neo4j_results(results: list[dict], *, truncate: bool = True) -> str:
    """Format a list of Neo4j result dicts into a human-readable summary string.

    Args:
        results: List of result dicts as returned by query_knowledge_base.
        truncate: When True, truncates each body to _MAX_BODY_CHARS characters.

    Returns:
        A formatted string summarising the best practices found, or a
        "no results" message when the list is empty.
    """
    if not results:
        return "No existing best practices found in the knowledge base."

    seen_names: set[str] = set()
    unique: list[dict] = []
    for node in results:
        name = node.get("name", "")
        if name not in seen_names:
            seen_names.add(name)
            unique.append(node)
    results = unique

    display_names: list[str] = []
    seen_dn: set[str] = set()
    for node in results:
        dn = node.get("display_name", "")
        if dn and dn not in seen_dn:
            seen_dn.add(dn)
            display_names.append(dn)

    parts: list[str] = []
    if display_names:
        tech_list = ", ".join(display_names)
        parts.append(f"Found {len(results)} best practice(s) for: {tech_list}\n")

    cumulative_chars = 0
    for i, node in enumerate(results, start=1):
        title = node.get("title", "Untitled")
        body = node.get("body", "")
        if truncate and len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "..."

        # Include version context when available
        display_name = node.get("display_name", "")
        version = node.get("version", "")
        if display_name and version and version != "unversioned":
            header = f'{i}. "{title}" ({display_name} v{version})'
        elif display_name:
            header = f'{i}. "{title}" ({display_name})'
        else:
            header = f"{i}. {title}"

        entry = f"{header}\n{body}"

        if cumulative_chars + len(entry) > _MAX_TOTAL_CHARS:
            remaining = len(results) - i + 1
            parts.append(f"({remaining} additional result(s) omitted for size)")
            break

        cumulative_chars += len(entry)
        parts.append(entry)

    return "\n\n".join(parts)
