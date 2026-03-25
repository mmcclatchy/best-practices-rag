from typing import Any

from neo4j import GraphDatabase


class GraphStore:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    def structured_query(
        self, query: str, *, param_map: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(
            query, parameters_=param_map or {}, database_="neo4j"
        )  # type: ignore[arg-type]
        return [dict(record) for record in records]

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
