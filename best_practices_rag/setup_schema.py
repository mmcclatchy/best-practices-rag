"""Apply the canonical graph schema to Neo4j idempotently.

Creates uniqueness constraints and property indexes for the BestPractice,
Technology, and Pattern node labels using CREATE ... IF NOT EXISTS syntax so
the script can be run multiple times without errors.

Usage:
    uv run python scripts/setup_schema.py
"""

import logging
import sys

import neo4j
from neo4j import GraphDatabase

from best_practices_rag.config import get_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Uniqueness constraints ensure no two nodes of the same label share an id.
CONSTRAINTS: list[tuple[str, str]] = [
    (
        "constraint_best_practice_id",
        "CREATE CONSTRAINT constraint_best_practice_id IF NOT EXISTS "
        "FOR (n:BestPractice) REQUIRE n.id IS UNIQUE",
    ),
    (
        "constraint_technology_id",
        "CREATE CONSTRAINT constraint_technology_id IF NOT EXISTS "
        "FOR (n:Technology) REQUIRE n.id IS UNIQUE",
    ),
    (
        "constraint_pattern_id",
        "CREATE CONSTRAINT constraint_pattern_id IF NOT EXISTS "
        "FOR (n:Pattern) REQUIRE n.id IS UNIQUE",
    ),
]

# Property indexes speed up MATCH queries that filter on these fields.
INDEXES: list[tuple[str, str]] = [
    (
        "index_best_practice_name",
        "CREATE INDEX index_best_practice_name IF NOT EXISTS "
        "FOR (n:BestPractice) ON (n.name)",
    ),
    (
        "index_best_practice_category",
        "CREATE INDEX index_best_practice_category IF NOT EXISTS "
        "FOR (n:BestPractice) ON (n.category)",
    ),
    (
        "index_technology_name",
        "CREATE INDEX index_technology_name IF NOT EXISTS "
        "FOR (n:Technology) ON (n.name)",
    ),
]

# Fulltext index for BM25 keyword search (replaces substring CONTAINS matching).
FULLTEXT_INDEXES: list[tuple[str, str]] = [
    (
        "bp_fulltext",
        "CREATE FULLTEXT INDEX bp_fulltext IF NOT EXISTS "
        "FOR (n:__Entity__) ON EACH [n.title, n.body]",
    ),
]


def apply_schema(driver: neo4j.Driver) -> None:
    # All Cypher strings in CONSTRAINTS / INDEXES are hardcoded literal
    # constants. The Neo4j driver stubs require LiteralString for query_
    # to guard against injection; the type: ignore comments acknowledge
    # these values are safe constants, not user-supplied strings.
    for name, cypher in CONSTRAINTS:
        driver.execute_query(cypher, database_="neo4j")  # type: ignore[arg-type]
        logger.info("Constraint applied: %s", name)

    for name, cypher in INDEXES:
        driver.execute_query(cypher, database_="neo4j")  # type: ignore[arg-type]
        logger.info("Index applied: %s", name)

    for name, cypher in FULLTEXT_INDEXES:
        driver.execute_query(cypher, database_="neo4j")  # type: ignore[arg-type]
        logger.info("Fulltext index applied: %s", name)


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
    )

    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", settings.neo4j_uri)

        apply_schema(driver)

        logger.info(
            "Schema setup complete — %d constraints, %d property indexes, "
            "%d fulltext indexes applied.",
            len(CONSTRAINTS),
            len(INDEXES),
            len(FULLTEXT_INDEXES),
        )
    except Exception:
        logger.exception("Schema setup failed")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
