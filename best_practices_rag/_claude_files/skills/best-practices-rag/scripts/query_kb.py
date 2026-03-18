#!/usr/bin/env python3

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from best_practices_rag.config import get_settings
from best_practices_rag.graph_store import GraphStore
from best_practices_rag.knowledge_base import (
    query_knowledge_base,
    summarize_neo4j_results,
)
from best_practices_rag.logging_setup import configure_skill_logging


configure_skill_logging()
logger = logging.getLogger(__name__)

MAX_AGE_DAYS: int = 90


def _load_current_versions(references_dir: Path) -> dict[str, str]:
    text = (references_dir / "tech-versions.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", text, re.MULTILINE)
    return {
        tech.strip().lower(): version.strip()
        for tech, version in rows
        if tech.strip() not in ("Technology", "---", "")
    }


# Returns structured staleness info instead of a bare boolean.
# Keys: is_stale (bool), reason ("version_mismatch"|"max_age"|"no_version_info"|None),
#   stale_technologies (list[str]), fresh_technologies (list[str]),
#   version_deltas (dict[str, dict] — tech -> {stored, current}),
#   document_age_days (int | None)
def _check_staleness(
    result: dict[str, Any], current_versions: dict[str, str]
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "is_stale": False,
        "reason": None,
        "stale_technologies": [],
        "fresh_technologies": [],
        "version_deltas": {},
        "document_age_days": None,
    }

    # Compute document age
    synthesized_at = result.get("synthesized_at", "")
    if synthesized_at:
        try:
            synth_dt = datetime.fromisoformat(synthesized_at)
            age_days = (datetime.now(timezone.utc) - synth_dt).days
            info["document_age_days"] = age_days
        except (ValueError, TypeError):
            pass

    # Check tech versions
    raw = result.get("tech_versions_at_synthesis", "")
    if not raw:
        info["is_stale"] = True
        info["reason"] = "no_version_info"
        return info

    try:
        stored: dict[str, str] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        info["is_stale"] = True
        info["reason"] = "no_version_info"
        return info

    for tech, stored_ver in stored.items():
        current_ver: str | None = current_versions.get(tech)
        if current_ver is None:
            # Tech not in versions table — cannot verify staleness, treat as fresh.
            info["fresh_technologies"].append(tech)
        elif current_ver != stored_ver:
            info["stale_technologies"].append(tech)
            info["version_deltas"][tech] = {
                "stored": stored_ver,
                "current": current_ver,
            }
        else:
            info["fresh_technologies"].append(tech)

    if info["stale_technologies"]:
        info["is_stale"] = True
        info["reason"] = "version_mismatch"
        return info

    # Check document age
    if (
        info["document_age_days"] is not None
        and info["document_age_days"] > MAX_AGE_DAYS
    ):
        info["is_stale"] = True
        info["reason"] = "max_age"
        return info

    return info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query Neo4j knowledge base for best practices"
    )
    parser.add_argument(
        "--tech", required=True, help="Comma-separated technology names"
    )
    parser.add_argument(
        "--topics", required=True, help="Comma-separated topic keywords"
    )
    parser.add_argument(
        "--languages", default=None, help="Comma-separated language names (optional)"
    )
    parser.add_argument(
        "--include-bodies",
        action="store_true",
        default=False,
        help="Include body fields for all non-stale results (not just stale ones)",
    )
    args = parser.parse_args()
    logger.debug(
        "query_kb invoked — tech=%r topics=%r languages=%r include_bodies=%r",
        args.tech,
        args.topics,
        args.languages,
        args.include_bodies,
    )

    tech_names = [t.strip() for t in args.tech.split(",") if t.strip()]
    topic_keywords = [t.strip().lower() for t in args.topics.split(",") if t.strip()]
    lang_names = (
        [lang.strip() for lang in args.languages.split(",") if lang.strip()]
        if args.languages
        else None
    )

    settings = get_settings()
    graph_store = GraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
    )

    current_versions = _load_current_versions(
        Path("./.claude/skills/best-practices-rag/references")
    )

    query = " ".join(tech_names + topic_keywords)
    results = query_knowledge_base(
        query=query,
        graph_store=graph_store,
        tech_names=tech_names,
        topic_keywords=topic_keywords,
        lang_names=lang_names,
    )

    for result in results:
        staleness = _check_staleness(result, current_versions)
        result["is_stale"] = staleness["is_stale"]
        result["staleness_reason"] = staleness["reason"]
        result["stale_technologies"] = staleness["stale_technologies"]
        result["fresh_technologies"] = staleness["fresh_technologies"]
        result["version_deltas"] = staleness["version_deltas"]
        result["document_age_days"] = staleness["document_age_days"]

    summary = summarize_neo4j_results(results)

    if args.include_bodies:
        slim_results = results
    else:
        slim_results = [
            {k: v for k, v in r.items() if k != "body" or r.get("is_stale")}
            for r in results
        ]

    logger.debug("query_kb complete — %d results returned", len(results))
    output = {
        "count": len(results),
        "results": slim_results,
        "summary": summary,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
