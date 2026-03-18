#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from pathlib import Path

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from best_practices_rag.config import get_settings
from best_practices_rag.logging_setup import configure_skill_logging
from best_practices_rag.parser import build_synthesized_bundle
from best_practices_rag.storage import store_results


configure_skill_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Store synthesized best practice into Neo4j"
    )
    parser.add_argument(
        "--tech", required=True, help="Comma-separated technology names"
    )
    parser.add_argument("--query", required=True, help="Original query string")
    parser.add_argument(
        "--content-file",
        required=True,
        help="Path to file containing synthesized markdown content",
    )
    parser.add_argument(
        "--source-urls", default=None, help="Comma-separated source URLs (optional)"
    )
    parser.add_argument(
        "--languages", default=None, help="Comma-separated language names (optional)"
    )
    parser.add_argument(
        "--tech-versions",
        default=None,
        help="JSON string of {tech: version} at synthesis time (optional)",
    )
    parser.add_argument(
        "--source-tiers",
        default=None,
        help="JSON string of {url: tier} mapping source URLs to quality tiers (optional)",
    )
    args = parser.parse_args()
    logger.debug(
        "store_result invoked — tech=%r query=%r content_file=%r source_urls=%r languages=%r tech_versions=%r source_tiers=%r",
        args.tech,
        args.query,
        args.content_file,
        args.source_urls,
        args.languages,
        args.tech_versions,
        args.source_tiers,
    )

    tech_names = [t.strip() for t in args.tech.split(",") if t.strip()]
    source_urls = (
        [u.strip() for u in args.source_urls.split(",") if u.strip()]
        if args.source_urls
        else []
    )
    lang_names = (
        [lang.strip() for lang in args.languages.split(",") if lang.strip()]
        if args.languages
        else None
    )
    tech_versions = json.loads(args.tech_versions) if args.tech_versions else None
    source_tiers = json.loads(args.source_tiers) if args.source_tiers else None

    content_path = Path(args.content_file)
    synthesized_content = content_path.read_text(encoding="utf-8")

    bundle = build_synthesized_bundle(
        synthesized_content=synthesized_content,
        tech_names=tech_names,
        source_urls=source_urls,
        query=args.query,
        lang_names=lang_names,
        tech_versions=tech_versions,
        source_tiers=source_tiers,
    )

    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    node_name = bp_nodes[0].name if bp_nodes else ""

    settings = get_settings()
    graph_store = Neo4jPropertyGraphStore(
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
        url=settings.neo4j_uri,
    )

    nodes_count = store_results(bundle, graph_store)

    logger.debug(
        "store_result complete — node_name=%r nodes=%d relations=%d",
        node_name,
        nodes_count,
        len(bundle.relations),
    )
    output = {
        "stored": True,
        "node_name": node_name,
        "nodes_count": nodes_count,
        "relations_count": len(bundle.relations),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
