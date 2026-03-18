#!/usr/bin/env python3

import argparse
import json
import logging
import sys

from best_practices_rag.logging_setup import configure_skill_logging
from best_practices_rag.search import search_best_practices


configure_skill_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Exa for best practices")
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument(
        "--exclude-domains",
        default=None,
        help="Comma-separated domains to exclude (optional)",
    )
    parser.add_argument(
        "--cutoff-date",
        default=None,
        help="ISO date string for start_published_date filter (optional)",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=10,
        help="Number of Exa results to request (default: 10)",
    )
    parser.add_argument(
        "--top-n", type=int, default=5, help="Number of top results (default: 5)"
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Exa category filter (e.g. 'github', 'blog', 'paper') (optional)",
    )
    args = parser.parse_args()
    logger.debug(
        "search_exa invoked — query=%r exclude_domains=%r cutoff_date=%r num_results=%d top_n=%d category=%r",
        args.query,
        args.exclude_domains,
        args.cutoff_date,
        args.num_results,
        args.top_n,
        args.category,
    )

    exclude_domains = (
        [d.strip() for d in args.exclude_domains.split(",") if d.strip()]
        if args.exclude_domains
        else None
    )

    results = search_best_practices(
        query=args.query,
        num_results=args.num_results,
        exclude_domains=exclude_domains,
        start_published_date=args.cutoff_date,
        category=args.category,
    )

    logger.debug(
        "search_exa complete — %d total results, returning top %d",
        len(results),
        args.top_n,
    )
    top_results = results[: args.top_n]
    output = {
        "count": len(results),
        "results": [
            {
                "url": r.url,
                "title": r.title,
                "summary": r.summary,
                "published_date": r.published_date,
                "text": r.text,
            }
            for r in top_results
        ],
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
