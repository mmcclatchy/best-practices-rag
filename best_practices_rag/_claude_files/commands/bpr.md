# Best Practices Research — Research Mode

Use this command to conduct in-depth research on software engineering topics, focusing on architectural rationale, design tradeoffs, and deep technical understanding. Invoke as `/bpr <query>`.

## Usage

```text
/bpr $ARGUMENTS
```

## Configuration

<!-- Output directory for saved best-practices documents. Change this path to relocate output. -->
Output directory: `.best-practices/`

## Workflow

Execute each step in order. Step 5 is the **gap path** and runs only when the knowledge base does not adequately cover the query.

### Step 1 — Extract technologies and topics

Parse `$ARGUMENTS`. Identify:
- Technology names (e.g., `fastapi`, `sqlalchemy`, `neo4j`)
- Topic keywords (e.g., `async`, `session management`, `connection pooling`)
- Language names if mentioned (e.g., `python`)
- `--force-refresh` flag — if present, skip Steps 3-4 entirely and proceed directly to the gap path (Step 5). Remove the flag from the query before using `$ARGUMENTS` elsewhere.

### Step 2 — Look up current versions

Read `./.claude/skills/best-practices-rag/references/tech-versions.md`.

For each technology identified in Step 1:
- Note the current version to append to Exa queries (e.g., `"FastAPI 0.116"`)
- Note the Release Date to derive `--cutoff-date` (format: `YYYY-01-01`)
- Record the full `{tech: version}` mapping as `TECH_VERSIONS_JSON` for use in Step 5
- If a technology is NOT found in the table, omit it from `TECH_VERSIONS_JSON` entirely — do not use `"latest"`, `"unknown"`, or any placeholder string
- If NO technologies are found in the table, set `TECH_VERSIONS_JSON` to `{}`; derive `--cutoff-date` as `(current year - 2)-01-01`

Compute the output file path:
- `OUTPUT_SLUG` = sorted tech names joined by `-` + `-` + topic keywords joined by `-`, truncated to 60 characters, then append `-research` (e.g., `fastapi-sqlalchemy-async-session-management-research`)
- `OUTPUT_FILE` = `.best-practices/<OUTPUT_SLUG>.md`

### Step 3 — Query the knowledge base

If `--force-refresh` was set in Step 1, skip this step and Step 4 entirely. Set `staleness_reason` to `"force_refresh"` and proceed to Step 5.

```bash
uv run ./.claude/skills/best-practices-rag/scripts/query_kb.py \
  --tech "<comma-separated tech names>" \
  --topics "<comma-separated topic keywords>" \
  [--languages "<comma-separated language names>"]
```

Parse the JSON from stdout: `{ "count": N, "results": [...], "summary": "..." }`.

Each result includes staleness fields: `is_stale`, `staleness_reason`, `stale_technologies`, `fresh_technologies`, `version_deltas`, `document_age_days`.

From the stdout, extract and retain ONLY:
- `count` — number of results
- `is_stale` flag for each result
- `staleness_reason` for stale results (one of: `"version_mismatch"`, `"max_age"`, `"no_version_info"`)
- `stale_technologies` and `version_deltas` for stale results — forwarded to bp-gap-handler
- `body` of any result where `is_stale: true` — passed as `STALE_CONTEXT_BODY` in Step 5

Do NOT retain the full raw JSON or body fields from non-stale results.

### Step 4 — Assess coverage

Compute:
- `COVERED_TECHS` = union of `fresh_technologies` across all results where `is_stale: false`
- `UNCOVERED_TECHS` = tech names from Step 1 that are NOT in `COVERED_TECHS`

**Full gap** (count == 0 OR all results stale): proceed to Step 5.
Pass stale result bodies as `STALE_CONTEXT_BODY` if any exist.

**Partial gap** (count > 0, at least one fresh result, but `UNCOVERED_TECHS` is not empty):
Proceed to Step 5. Pass `UNCOVERED_TECHS` as `UNCOVERED_TECH` in the gap handler call.
The gap handler should focus research on the uncovered technologies only.
After it runs, the synthesizer in Step 5.5 will pull both the existing and new KB content together.

**Full coverage** (count > 0, at least one fresh result, `UNCOVERED_TECHS` is empty):
Skip to Step 5.5.

### Step 5 — Launch bp-gap-handler [gap path]

Build the versioned primary query string and append `"official documentation"`: e.g., `"FastAPI 0.116 async session management SQLAlchemy 2.0 official documentation"`.

Delegate to the `bp-gap-handler` agent using Task:

```text
Task(bp-gap-handler):
MODE: research
TECH: <comma-separated tech names from Step 1>
QUERY: $ARGUMENTS
TECH_VERSIONS_JSON: <JSON string from Step 2, e.g. {"fastapi":"0.116","sqlalchemy":"2.0"}>
CUTOFF_DATE: <YYYY-01-01 derived in Step 2>
PRIMARY_QUERY: <versioned query string built above>
OUTPUT_FILE: <OUTPUT_FILE from Step 2>
LANGUAGES: <comma-separated language names if identified in Step 1, omit if none>
STALE_CONTEXT_BODY: <body text of stale KB results from Step 3, omit if none>
STALE_TECHNOLOGIES: <comma-separated list from Step 3 staleness check, omit if none>
VERSION_DELTAS: <JSON string from Step 3, e.g. {"sqlalchemy":{"stored":"2.0","current":"2.1"}}, omit if none>
UNCOVERED_TECH: <comma-separated tech names from UNCOVERED_TECHS, omit if full gap>
```

Wait for `bp-gap-handler` to return `"Synthesis complete. Output: <OUTPUT_FILE>"`.

### Step 5.5 — Response synthesis (always runs)

After Step 4 (cache hit) or after Step 5 (gap fill), invoke `bp-synthesizer`:

```text
Task(bp-synthesizer):
MODE: research
TECH: <comma-separated tech names from Step 1>
TOPICS: <comma-separated topic keywords from Step 1>
QUERY: $ARGUMENTS
OUTPUT_FILE: <OUTPUT_FILE from Step 2>
LANGUAGES: <comma-separated language names if identified in Step 1, omit if none>
```

Wait for `bp-synthesizer` to return `"Synthesis complete. Output: <OUTPUT_FILE>"`.

### Step 6 — Output to user

Read `OUTPUT_FILE` (computed in Step 2) and present it as formatted markdown.

## References

- Synthesis format (codegen): `./.claude/skills/best-practices-rag/references/synthesis-format-codegen.md`
- Synthesis format (research): `./.claude/skills/best-practices-rag/references/synthesis-format-research.md`
- Technology versions: `./.claude/skills/best-practices-rag/references/tech-versions.md`
