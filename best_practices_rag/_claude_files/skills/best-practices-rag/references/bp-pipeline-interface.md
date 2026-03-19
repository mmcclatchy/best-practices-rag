# bp-pipeline Interface Reference

Reference document for callers that dispatch `bp-pipeline` via `Task(bp-pipeline)`. Intended for use by `/bp`, `/bpr`, and respec-phase Step 7.5 parallel dispatch.

## Input Interface

All fields are strings unless noted. Optional fields may be omitted from the Task block entirely.

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

## Minimal Task Block Example

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

## Cache-Hit Task Block Example

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

## Concurrency Notes

bp-pipeline instances are stateless per invocation. All large-data operations (Exa results, context7 documentation, synthesis working notes) live exclusively in the ephemeral subagent context and are never shared with the caller or other instances.

This design makes parallel dispatch safe: two bp-pipeline invocations for different `TECH` values will not interfere with each other. The only shared resource is the Neo4j KB, which is written by `store_result.py` — each invocation writes a separate node scoped to its own `STORE_TECH`, so concurrent writes do not collide.

**Parallel dispatch pattern for respec-phase Step 7.5:**

```text
Parallel:
  Task(bp-pipeline): [tech-A params]
  Task(bp-pipeline): [tech-B params]
Wait for both BP_PIPELINE_COMPLETE signals before proceeding.
```

Each instance writes to a distinct `OUTPUT_FILE` and a distinct KB node.
