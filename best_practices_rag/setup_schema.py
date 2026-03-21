import logging
import sys
from pathlib import Path

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from neo4j_python_migrations.executor import Executor

from best_practices_rag.config import get_settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

_MIGRATIONS_PATH = Path(__file__).parent / "migrations"


def _ensure_schema(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "SHOW INDEXES YIELD name WHERE name = 'bp_fulltext' RETURN count(*) AS cnt",
        database_="neo4j",
    )
    if records and records[0]["cnt"] > 0:
        return

    logger.info("Fulltext index missing — applying schema directly")
    migration_file = _MIGRATIONS_PATH / "V0001__initial_schema.cypher"
    for statement in migration_file.read_text().strip().split(";"):
        statement = statement.strip()
        if statement:
            driver.execute_query(statement, database_="neo4j")  # type: ignore[arg-type]
    logger.info("Schema applied directly")


def run_migrations() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
    )
    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", settings.neo4j_uri)
        Executor(driver, migrations_path=_MIGRATIONS_PATH).migrate()
        _ensure_schema(driver)
        logger.info("Schema migrations complete.")
    finally:
        driver.close()


def main() -> None:
    try:
        run_migrations()
    except (AuthError, ServiceUnavailable) as exc:
        logger.error("Schema setup failed: %s", exc)
        sys.exit(1)
    except Exception:
        logger.exception("Schema setup failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
