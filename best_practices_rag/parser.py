"""Parse Exa search results into graph nodes and relations.

Tags each result with user-provided technology names instead of running
LLM extraction — eliminates connection drops, extraction noise, and
mis-tagging from incidental mentions.

Schema:
  BestPractice -[:APPLIES_TO]-> TechVersion -[:VERSION_OF]-> Technology
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from llama_index.core.graph_stores.types import EntityNode, Relation
from pydantic import BaseModel

from best_practices_rag.search import ExaResult


logger = logging.getLogger(__name__)


class TechExtraction(BaseModel):
    name: str
    version: str | None = None


_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "about",
        "against",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "because",
        "but",
        "and",
        "or",
        "if",
        "while",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "its",
        "his",
        "her",
        "their",
        "our",
        "your",
        "my",
        # Domain stop words
        "best",
        "practices",
        "patterns",
        "using",
        "integrating",
        "guide",
        "tutorial",
        "approach",
        "strategies",
        "strategy",
    }
)


@dataclass
class GraphBundle:
    nodes: list[EntityNode] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


def _normalize_url(url: str) -> str:
    if "#" in url:
        url = url[: url.index("#")]
    if "?" in url:
        url = url[: url.index("?")]
    url = url.rstrip("/")
    return url


def _build_tech_relations(
    bp_name: str, tech_names: list[str]
) -> tuple[list[EntityNode], list[Relation]]:
    nodes: list[EntityNode] = []
    relations: list[Relation] = []
    tech_nodes: dict[str, EntityNode] = {}
    version_nodes: dict[str, EntityNode] = {}

    for tech_name in tech_names:
        tech = TechExtraction(name=tech_name)
        tech_key = tech.name.lower()
        version = tech.version or "unversioned"
        version_key = f"{tech_key}:{version}"

        if tech_key not in tech_nodes:
            tech_node = EntityNode(
                label="Technology",
                name=tech_key,
                properties={"display_name": tech.name},
            )
            tech_nodes[tech_key] = tech_node
            nodes.append(tech_node)

        if version_key not in version_nodes:
            tv_node = EntityNode(
                label="TechVersion",
                name=version_key,
                properties={
                    "tech": tech_key,
                    "version": version,
                },
            )
            version_nodes[version_key] = tv_node
            nodes.append(tv_node)

            relations.append(
                Relation(
                    label="VERSION_OF",
                    source_id=version_key,
                    target_id=tech_key,
                )
            )

        relations.append(
            Relation(
                label="APPLIES_TO",
                source_id=bp_name,
                target_id=version_key,
            )
        )

    return nodes, relations


async def parse_results(
    results: list[ExaResult], *, tech_names: list[str]
) -> GraphBundle:
    """Parse Exa results into a GraphBundle of nodes and relations.

    Uses user-provided tech_names to create Technology / TechVersion nodes
    and APPLIES_TO edges — no LLM extraction calls.
    """
    logger.info("Parsing %d Exa results", len(results))
    seen_urls: set[str] = set()
    unique_results = []
    for r in results:
        key = _normalize_url(r.url)
        if key not in seen_urls:
            seen_urls.add(key)
            unique_results.append(r)

    shared_techs = [TechExtraction(name=t) for t in tech_names]
    all_techs: list[list[TechExtraction]] = [shared_techs for _ in unique_results]

    nodes: list[EntityNode] = []
    relations: list[Relation] = []
    tech_node_registry: dict[str, EntityNode] = {}
    version_node_registry: dict[str, EntityNode] = {}

    for result in unique_results:
        logger.debug(
            "Parsing result — url=%r title=%r summary_length=%d",
            result.url,
            result.title,
            len(result.summary or ""),
        )
        bp_node = EntityNode(
            label="BestPractice",
            name=_normalize_url(result.url),
            properties={
                "title": result.title,
                "body": result.summary,
                "source_url": result.url,
                "published_date": result.published_date,
            },
        )
        nodes.append(bp_node)

    bp_nodes = [n for n in nodes if n.label == "BestPractice"]
    for bp_node, result, techs in zip(bp_nodes, unique_results, all_techs):
        logger.info(
            "Result %r — extracted %d technologies",
            result.url,
            len(techs),
        )
        for tech in techs:
            tech_key = tech.name.lower()
            version = tech.version or "unversioned"
            version_key = f"{tech_key}:{version}"
            logger.debug(
                "  tech=%r version=%r version_key=%r", tech.name, version, version_key
            )

            if tech_key not in tech_node_registry:
                tech_node = EntityNode(
                    label="Technology",
                    name=tech_key,
                    properties={"display_name": tech.name},
                )
                tech_node_registry[tech_key] = tech_node
                nodes.append(tech_node)

            if version_key not in version_node_registry:
                tv_node = EntityNode(
                    label="TechVersion",
                    name=version_key,
                    properties={
                        "tech": tech_key,
                        "version": version,
                    },
                )
                version_node_registry[version_key] = tv_node
                nodes.append(tv_node)

                relations.append(
                    Relation(
                        label="VERSION_OF",
                        source_id=version_key,
                        target_id=tech_key,
                    )
                )

            relations.append(
                Relation(
                    label="APPLIES_TO",
                    source_id=bp_node.name,
                    target_id=version_key,
                )
            )

    bp_count = sum(1 for n in nodes if n.label == "BestPractice")
    tech_count = len(tech_node_registry)
    tv_count = len(version_node_registry)
    rel_count = len(relations)
    logger.info(
        "Parsed — %d BestPractice, %d Technology, %d TechVersion nodes, %d relations",
        bp_count,
        tech_count,
        tv_count,
        rel_count,
    )
    return GraphBundle(nodes=nodes, relations=relations)


def build_synthesized_bundle(
    synthesized_content: str,
    tech_names: list[str],
    source_urls: list[str],
    query: str,
    lang_names: list[str] | None = None,
    tech_versions: dict[str, str] | None = None,
    source_tiers: dict[str, str] | None = None,
) -> GraphBundle:
    """Build a GraphBundle containing one synthesized BestPractice node."""
    first_line = query.split("\n")[0].lower()
    slug_words = [w for w in first_line.split() if len(w) >= 3 and w not in _STOP_WORDS]
    topic_slug = "-".join(slug_words)[:60]

    sorted_techs = ":".join(sorted(t.lower() for t in tech_names))
    bp_name = f"bp:{sorted_techs}:{topic_slug}"

    title = query.split("\n")[0][:80]

    bp_node = EntityNode(
        label="BestPractice",
        name=bp_name,
        properties={
            "title": title,
            "body": synthesized_content,
            "source_urls": ", ".join(source_urls),
            "synthesized_at": datetime.now(timezone.utc).isoformat(),
            "languages": ", ".join(lang_names) if lang_names else "",
            "tech_versions_at_synthesis": json.dumps(tech_versions)
            if tech_versions
            else "",
            "source_tiers": json.dumps(source_tiers) if source_tiers else "",
        },
    )

    tech_nodes, tech_relations = _build_tech_relations(bp_name, tech_names)

    logger.info(
        "Built synthesized bundle — name=%r techs=%s sources=%d",
        bp_name,
        tech_names,
        len(source_urls),
    )

    return GraphBundle(
        nodes=[bp_node] + tech_nodes,
        relations=tech_relations,
    )
