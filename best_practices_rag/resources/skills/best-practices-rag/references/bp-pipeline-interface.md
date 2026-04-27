# bp-pipeline Interface Reference

Reference document for callers that dispatch `bp-pipeline`. Intended for use by `/bp`, `/bpr`, and respec-phase Step 7.5 parallel dispatch.

Claude Code and OpenCode dispatch `bp-pipeline` with `Task(bp-pipeline)`. Codex dispatches it as a custom agent from `.codex/agents/bp-pipeline.toml`.

## Input Interface

All fields are strings unless noted. Optional fields may be omitted from the Task block or agent prompt entirely.

| Field | Required | Type | Description |
|---|---|---|---|
| `MODE` | Required | `codegen` or `research` | Drives final synthesis format in Step 7 |
| `TECH` | Required | comma-separated string | All technology names from the user query |
| `QUERY` | Required | string | Original user query string, verbatim |
| `TECH_VERSIONS_JSON` | Required | JSON string | `{"tech": "version"}` mapping; use `{}` if no versions found |
| `CUTOFF_DATE` | Required (gap path) | `YYYY-01-01` string | Derived from earliest relevant tech release date |
| `PRIMARY_QUERY` | Required (gap path) | string | Versioned query with `"official documentation"` appended |
| `OUTPUT_FILE` | Required | workspace-relative path | e.g., `.best-practices/fastapi-async-codegen.md` |
| `TOPICS` | Required | comma-separated string | Topic keywords from query parsing |
| `LANGUAGES` | Optional | comma-separated string | e.g., `"python"` — omit if not mentioned |
| `LANGUAGE_AGNOSTIC` | Optional | `"true"` string | Mutually exclusive with LANGUAGES — synthesis uses pseudocode |
| `STALE_CONTEXT_BODY` | Optional | string | Body text of stale KB entries; omit if none |
| `STALE_TECHNOLOGIES` | Optional | comma-separated string | Technologies whose versions changed |
| `VERSION_DELTAS` | Optional | JSON string | `{"tech":{"stored":"x","current":"y"}}` |
| `UNCOVERED_TECH` | Optional | comma-separated string | Gap technologies only; omit on full coverage or full gap |
| `COVERED_TECHS` | Optional | comma-separated string | Fresh-KB tech names; omit on full gap |
| `ALL_QUERIED_TECHS` | Optional | comma-separated string | All tech names from Step 1 — used to compute EXTRA_TECHS |

### Path Routing Summary

| Scenario | UNCOVERED_TECH | COVERED_TECHS | ALL_QUERIED_TECHS | bp-pipeline behavior |
|---|---|---|---|---|
| Full gap | omit | omit | include | Runs Steps 0–7 (all tech) |
| Partial gap | include (gap techs) | include (fresh techs) | include | Runs Steps 0–6 for gap techs, Step 7 across all |
| Cache hit | omit | include (all techs) | include | Skips to Step 7 directly |

## Completion Signal

bp-pipeline returns exactly one line of output:

```text
BP_PIPELINE_COMPLETE. Output: <OUTPUT_FILE>. Extra: <EXTRA_TECHS>. KB_Stored: <true|false>
```

| Signal Field | Format | Description |
|---|---|---|
| `Output` | workspace-relative path | Path to the synthesized document — use this, not the path computed by the caller |
| `Extra` | comma-separated string (may be empty) | Tech names in KB results that the user did not query for |
| `KB_Stored` | `true` or `false` | Whether store_result.py was called (false on cache-hit path) |

**Error handling**: If bp-pipeline output does not contain `BP_PIPELINE_COMPLETE`, the caller must surface an explicit error to the user rather than silently continuing with a missing or wrong output path.

## Claude/OpenCode Task Examples

### Minimal Task Block Example

```text
Task(bp-pipeline):
MODE: codegen
TECH: fastapi,sqlalchemy
QUERY: async session management with SQLAlchemy 2.0
TECH_VERSIONS_JSON: {"fastapi":"0.116","sqlalchemy":"2.0"}
CUTOFF_DATE: 2024-01-01
PRIMARY_QUERY: FastAPI 0.116 async session management SQLAlchemy 2.0 official documentation
OUTPUT_FILE: .best-practices/fastapi-sqlalchemy-async-session-management-codegen.md
TOPICS: async,session management
LANGUAGES: python
ALL_QUERIED_TECHS: fastapi,sqlalchemy
```

### Language-Agnostic Task Block Example

```text
Task(bp-pipeline):
MODE: research
TECH: redis
QUERY: caching strategies
TECH_VERSIONS_JSON: {"redis":"7.4"}
CUTOFF_DATE: 2024-01-01
PRIMARY_QUERY: Redis 7.4 caching strategies official documentation
OUTPUT_FILE: .best-practices/redis-caching-strategies-research.md
TOPICS: caching,strategies
LANGUAGE_AGNOSTIC: true
ALL_QUERIED_TECHS: redis
```

Note: `LANGUAGE_AGNOSTIC` and `LANGUAGES` are mutually exclusive. When `LANGUAGE_AGNOSTIC` is true, synthesis uses pseudocode for all code examples.

### Cache-Hit Task Block Example

```text
Task(bp-pipeline):
MODE: research
TECH: fastapi,sqlalchemy
QUERY: async session management with SQLAlchemy 2.0
TECH_VERSIONS_JSON: {"fastapi":"0.116","sqlalchemy":"2.0"}
OUTPUT_FILE: .best-practices/fastapi-sqlalchemy-async-session-management-research.md
TOPICS: async,session management
COVERED_TECHS: fastapi,sqlalchemy
ALL_QUERIED_TECHS: fastapi,sqlalchemy
```

Note: `CUTOFF_DATE`, `PRIMARY_QUERY`, and gap-related fields are omitted on the cache-hit path — bp-pipeline detects the absence of `UNCOVERED_TECH` and proceeds directly to Step 7.

## Codex Agent Dispatch

Codex installs `bp-pipeline` as a custom agent TOML file:

```text
~/.codex/agents/bp-pipeline.toml
```

Spawn or delegate to the `bp-pipeline` agent with the same input fields:

```text
Spawn/delegate to agent: bp-pipeline
MODE: codegen
TECH: fastapi,sqlalchemy
QUERY: async session management with SQLAlchemy 2.0
TECH_VERSIONS_JSON: {"fastapi":"0.116","sqlalchemy":"2.0"}
CUTOFF_DATE: 2024-01-01
PRIMARY_QUERY: FastAPI 0.116 async session management SQLAlchemy 2.0 official documentation
OUTPUT_FILE: .best-practices/fastapi-sqlalchemy-async-session-management-codegen.md
TOPICS: async,session management
LANGUAGES: python
ALL_QUERIED_TECHS: fastapi,sqlalchemy
```

Wait for the same `BP_PIPELINE_COMPLETE` signal before continuing.

## Concurrency Notes

bp-pipeline instances are stateless per invocation. All large-data operations (Exa results, context7 documentation, synthesis working notes) live exclusively in the ephemeral subagent context and are never shared with the caller or other instances.

This design makes parallel dispatch safe: two bp-pipeline invocations for different `TECH` values will not interfere with each other. The only shared resource is the Neo4j KB, which is written by `store_result.py` — each invocation writes a separate node scoped to its own `STORE_TECH`, so concurrent writes do not collide.

**Parallel dispatch pattern for Claude/OpenCode respec-phase Step 7.5:**

```text
Parallel:
  Task(bp-pipeline): [tech-A params]
  Task(bp-pipeline): [tech-B params]
Wait for both BP_PIPELINE_COMPLETE signals before proceeding.
```

For Codex, spawn/delegate to two `bp-pipeline` agent instances with distinct input prompts and wait for both `BP_PIPELINE_COMPLETE` signals before proceeding.

Each instance writes to a distinct `OUTPUT_FILE` and a distinct KB node.
