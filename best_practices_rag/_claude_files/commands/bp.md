# Best Practices Research

Use this command to search for software engineering best practices, technology integration patterns, framework usage guidance, and library configuration recommendations. Invoke as `/bp <query>`.

## Usage

```text
/bp $ARGUMENTS
```

## Configuration

<!-- Output directory for saved best-practices documents. Change this path to relocate output. -->
Output directory: `.best-practices/`

## Workflow

Execute each step in order. Steps 1–4 run in the main session and produce scalar parameters. Step 5 delegates all large-data work to bp-pipeline.

### Step 1 — Extract technologies and topics

Parse `$ARGUMENTS`. Identify:
- Technology names (e.g., `fastapi`, `sqlalchemy`, `neo4j`)
- Topic keywords (e.g., `async`, `session management`, `connection pooling`)
- Language names if mentioned (e.g., `python`)
- `--force-refresh` flag — if present, skip Steps 3-4 entirely and proceed directly to Step 5. Remove the flag from the query before using `$ARGUMENTS` elsewhere.

### Step 2 — Look up current versions

```bash
best-practices-rag lookup-versions --tech "<comma-separated tech names from Step 1>"
```

Parse the JSON:
- `tech_versions` → use directly as `TECH_VERSIONS_JSON` for Step 5
- `cutoff_date` → use as `CUTOFF_DATE`
- Technologies in `not_found` have no version entry — they are already absent from `tech_versions`
- If `tech_versions` is empty (no technologies found), `cutoff_date` defaults to `(current year - 2)-01-01`

Compute the output file path:

```bash
best-practices-rag generate-slug --tech "<comma-separated tech names>" --topics "<comma-separated topic keywords>"
```

- `OUTPUT_SLUG` = stdout from the command above
- `OUTPUT_FILE` = `.best-practices/<OUTPUT_SLUG>.md`

### Step 2.5 — Check file cache

If `--force-refresh` was set in Step 1, skip this step.

```bash
best-practices-rag check-file-cache \
  --file "<OUTPUT_FILE from Step 2>" \
  --model "<your model ID, e.g. claude-sonnet-4-6>"
```

Parse the JSON. If `hit` is `true`:
- Skip Steps 3–5 entirely
- Proceed directly to Step 6 — Output to user
- Prepend: `> **Cached:** Serving previously synthesized result.`

If `hit` is `false`, continue to Step 3.

### Step 3 — Query the knowledge base

If `--force-refresh` was set in Step 1, skip this step and Step 4 entirely. Set `staleness_reason` to `"force_refresh"` and proceed to Step 5.

```bash
best-practices-rag query-kb \
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
- `stale_technologies` and `version_deltas` for stale results — forwarded to bp-pipeline
- `body` of any result where `is_stale: true` — passed as `STALE_CONTEXT_BODY` in Step 5

Do NOT retain the full raw JSON or body fields from non-stale results.

### Step 4 — Assess coverage

Compute:
- `COVERED_TECHS` = union of `fresh_technologies` across all results where `is_stale: false`
- `UNCOVERED_TECHS` = tech names from Step 1 that are NOT in `COVERED_TECHS`
- `EXTRA_TECHS` = tech names in `COVERED_TECHS` that are NOT in the user-queried tech names from Step 1

**Full gap** (count == 0 OR all results stale): proceed to Step 5 (gap path).
Pass stale result bodies as `STALE_CONTEXT_BODY` if any exist. Omit `UNCOVERED_TECH` and `COVERED_TECHS` from the Task call.

**Partial gap** (count > 0, at least one fresh result, but `UNCOVERED_TECHS` is not empty):
Proceed to Step 5. Pass `UNCOVERED_TECHS` as `UNCOVERED_TECH` and `COVERED_TECHS` in the Task call.
bp-pipeline will focus gap research on the uncovered technologies only, then synthesize across all KB content.

**Full coverage** (count > 0, at least one fresh result, `UNCOVERED_TECHS` is empty):
Proceed to Step 5 (cache-hit path). Omit `UNCOVERED_TECH`. Pass `COVERED_TECHS` and `ALL_QUERIED_TECHS`.
bp-pipeline will skip Steps 0–6 and go directly to synthesis.

### Step 5 — Launch bp-pipeline

Build the versioned primary query string and append `"official documentation"`: e.g., `"FastAPI 0.116 async session management SQLAlchemy 2.0 official documentation"`.

Delegate to the `bp-pipeline` agent using Task:

```text
Task(bp-pipeline):
MODE: codegen
TECH: <comma-separated tech names from Step 1>
QUERY: $ARGUMENTS
TECH_VERSIONS_JSON: <JSON string from Step 2, e.g. {"fastapi":"0.116","sqlalchemy":"2.0"}>
CUTOFF_DATE: <YYYY-01-01 derived in Step 2>
PRIMARY_QUERY: <versioned query string built above>
OUTPUT_FILE: <OUTPUT_FILE from Step 2>
TOPICS: <comma-separated topic keywords from Step 1>
LANGUAGES: <comma-separated language names if identified in Step 1, omit if none>
STALE_CONTEXT_BODY: <body text of stale KB results from Step 3, omit if none>
STALE_TECHNOLOGIES: <comma-separated list from Step 3 staleness check, omit if none>
VERSION_DELTAS: <JSON string from Step 3, e.g. {"sqlalchemy":{"stored":"2.0","current":"2.1"}}, omit if none>
UNCOVERED_TECH: <comma-separated tech names from UNCOVERED_TECHS, omit if full coverage or full gap>
COVERED_TECHS: <comma-separated tech names from COVERED_TECHS, omit if full gap>
ALL_QUERIED_TECHS: <comma-separated tech names from Step 1>
```

Wait for bp-pipeline to return the completion signal:

```text
BP_PIPELINE_COMPLETE. Output: <OUTPUT_FILE>. Extra: <EXTRA_TECHS>. KB_Stored: <true|false>
```

If bp-pipeline output does NOT contain `BP_PIPELINE_COMPLETE`, surface a clear error to the user: "bp-pipeline did not return a completion signal. Check bp-pipeline output for errors." Do not silently continue.

Parse the signal:
- `OUTPUT_FILE` from the `Output:` field (use this path for Step 6 — do not reuse the path computed in Step 2)
- `EXTRA_TECHS_FROM_PIPELINE` from the `Extra:` field (comma-separated string, may be empty)

### Step 6 — Output to user

Read `OUTPUT_FILE` (from the bp-pipeline completion signal) and present it as formatted markdown.

If `EXTRA_TECHS_FROM_PIPELINE` is non-empty, prepend this blockquote before the document content:

> **Note:** These results cover [EXTRA_TECHS_FROM_PIPELINE joined by " + "] in addition to what you queried. This
> document assumes [EXTRA_TECHS_FROM_PIPELINE] as the implementation layer. Re-run with explicit technology names
> (e.g., `/bp fastapi redis async session`) for different patterns.

## References

- Synthesis format (codegen): `~/.claude/skills/best-practices-rag/references/synthesis-format-codegen.md`
- Synthesis format (research): `~/.claude/skills/best-practices-rag/references/synthesis-format-research.md`
- Technology versions: `~/.claude/skills/best-practices-rag/references/tech-versions.md`
- bp-pipeline interface: `~/.claude/skills/best-practices-rag/references/bp-pipeline-interface.md`
