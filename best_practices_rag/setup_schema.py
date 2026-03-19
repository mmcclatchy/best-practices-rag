import logging
import sys
from pathlib import Path

from neo4j import GraphDatabase
from neo4j_python_migrations.executor import Executor

from best_practices_rag.config import get_settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

_MIGRATIONS_PATH = Path(__file__).parent / "migrations"


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
    )
    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", settings.neo4j_uri)
        Executor(driver, migrations_path=_MIGRATIONS_PATH).migrate()
        logger.info("Schema migrations complete.")
    except Exception:
        logger.exception("Schema setup failed")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
