# Tech Versions

Reference table for deriving Exa search version strings and `--cutoff-date` values.

**How to derive `--cutoff-date`**: Use the Release Date of the technology's current major version from the table below, or fall back to `(current year - 2)` as `YYYY-01-01`, whichever is more recent. Format as `YYYY-01-01`.

| Technology | Version | Release Date | Key Changes |
| --- | --- | --- | --- |
| Python | 3.13 | 2024-10-01 | Free-threaded mode (experimental), improved error messages, new typing features |
| FastAPI | 0.116 | 2025-01-01 | Lifespan context manager replaces `@app.on_event`; use `async with` lifespan |
| SQLAlchemy | 2.0 | 2023-01-26 | 2.0-style queries required; `Session.execute()` replaces legacy `Query`; type-annotated models |
| LlamaIndex (llama-index-core) | 0.14 | 2025-01-01 | PropertyGraphStore API stable; `structured_query()` for raw Cypher |
| Neo4j Python driver | 5.28 | 2025-01-01 | Async driver (`AsyncGraphDatabase`); `ManagedTransaction` pattern |
| pydantic-settings | 2.13 | 2025-06-01 | `SettingsConfigDict` with `extra='ignore'`; `model_config` replaces inner `Config` class |
| pydantic | 2.12 | 2025-06-01 | `model_validator`, `field_validator` decorators; no `__root__` models |
| exa-py | 2.6 | 2025-10-01 | Single-call `exa.search()` with `contents` dict; `highlights` removed; use `summary=True` |
| beanie | 2.0 | 2024-01-01 | Dropped Motor dependency; uses PyMongo native async (`AsyncMongoClient`); `Document` model API stable |
| pymongo | 4.11 | 2024-10-01 | `AsyncMongoClient` introduced as Motor-free native async driver |
| alembic | 1.16 | 2025-01-01 | Async engine support via `run_sync`; `--autogenerate` improvements |
