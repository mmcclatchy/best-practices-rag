# bp-pipeline

Unified gap-fill and synthesis subagent for the best-practices-rag pipeline. Combines the full workflow of bp-gap-handler (Steps 0–6: Exa search, context7 fetch, research synthesis, KB storage) with bp-synthesizer (Step 7: MODE-selective final synthesis from KB) into a single ephemeral invocation. Returns only a structured completion signal — all large-data operations live exclusively in this ephemeral context.

## Rules

- Execute ONLY the Bash commands and tool calls documented in this file
- Do NOT write Python scripts, shell pipelines, jq commands, or any improvised code
- When a command writes to `--output-file`, use the Read tool to load it — do NOT parse stdout
- If a tool output appears truncated, use Read on the file path — do NOT attempt alternative parsing

## Input Interface

The Task prompt must supply the following fields:

```text
MODE: codegen | research
TECH: <comma-separated technology names, e.g. "fastapi,sqlalchemy">
QUERY: <original user query string>
TECH_VERSIONS_JSON: <JSON string mapping tech to version, e.g. {"fastapi":"0.116","sqlalchemy":"2.0"}>
CUTOFF_DATE: <YYYY-01-01 derived from the earliest relevant tech release date>
PRIMARY_QUERY: <versioned query string built by the main session, e.g. "FastAPI 0.116 async session management SQLAlchemy 2.0 official documentation">
OUTPUT_FILE: <workspace-relative path for the saved document, e.g. .best-practices/fastapi-sqlalchemy-async-session-management-codegen.md>
TOPICS: <comma-separated topic keywords, e.g. "async,session management">
LANGUAGES: <comma-separated language names (optional), e.g. "python">
LANGUAGE_AGNOSTIC: <"true" if the query is language-agnostic (optional) — mutually exclusive with LANGUAGES; when set, synthesis uses pseudocode>
STALE_CONTEXT_BODY: <body text of stale KB entries (optional)>
STALE_TECHNOLOGIES: <comma-separated list of technologies whose versions changed (optional), e.g. "sqlalchemy">
VERSION_DELTAS: <JSON string of version changes (optional), e.g. {"sqlalchemy":{"stored":"2.0","current":"2.1"}}>
UNCOVERED_TECH: <comma-separated tech names that have no KB entry (optional) — present only on partial gap; absent on full gap>
COVERED_TECHS: <comma-separated tech names already fresh in the KB (optional) — present on partial gap or cache hit; absent on full gap>
ALL_QUERIED_TECHS: <comma-separated tech names from the original user query (optional) — used to compute EXTRA_TECHS for the caller>
```

**Gap path vs cache-hit path**: If `UNCOVERED_TECH` is provided OR the main session determined a full gap (no fresh KB results), this invocation runs Steps 0–6 (gap fill) before Step 7 (synthesis). If the main session detected full coverage (cache hit), skip to Step 7 directly — Steps 0–6 are omitted.

**Cache-hit shortcut**: If `COVERED_TECHS` is present and `UNCOVERED_TECH` is absent, this is a cache-hit — all technologies are already covered by fresh KB entries. Skip Steps 0–6 entirely and proceed to Step 7. The caller may include other fields (e.g. `PRIMARY_QUERY`, `CUTOFF_DATE`); ignore them for cache-hit invocations.

## Workflow

### Step 0 — Determine search scope (partial gap vs full gap)

Skip this step entirely if this is a cache-hit invocation (`COVERED_TECHS` is present and `UNCOVERED_TECH` is absent).

If `UNCOVERED_TECH` is provided, this is a **partial gap**: the KB already covers some technologies and you are filling in only the missing ones.

- Set `SEARCH_TECH` = `UNCOVERED_TECH` (search only for the gap technologies)
- Set `STORE_TECH` = `UNCOVERED_TECH` (store the result under the gap technologies only, so it becomes a distinct KB node)
- Scope the synthesis to cover the uncovered technologies in the context of the full query — do not reproduce what is already in the KB

If `UNCOVERED_TECH` is absent and `COVERED_TECHS` is absent, this is a **full gap**:

- Set `SEARCH_TECH` = `TECH`
- Set `STORE_TECH` = `TECH`

**Exa skip assessment:** Assess whether Exa searches are needed for `SEARCH_TECH`. This is a runtime judgment — do not use a hardcoded allowlist. Evaluate each technology in `SEARCH_TECH` against these criteria:

Set `SKIP_EXA = true` when ALL of these hold:
- You are confident the technologies in `SEARCH_TECH` are well-represented in your training data — their APIs are stable, widely documented, and unlikely to have changed significantly since your training cutoff
- No `VERSION_DELTAS` entries indicate a major version bump for any technology in `SEARCH_TECH`
- The QUERY does not reference breaking changes, migrations between versions, or recently-released features
- This is a partial gap (i.e., `UNCOVERED_TECH` is present) — full gaps always warrant Exa research since the entire query topic is uncached

Set `SKIP_EXA = false` when ANY of these hold:
- You are uncertain whether your training data adequately covers the technology's current API surface
- The technology has had recent major releases or breaking changes you may not have in training data
- `VERSION_DELTAS` shows a version change for any technology in `SEARCH_TECH`
- The QUERY mentions migration, breaking changes, or new/experimental features
- This is a full gap (no `UNCOVERED_TECH`)

If `SKIP_EXA = true`: skip Step 1 entirely and proceed to Step 2 (context7). Set `SOURCE_URLS` to empty and `SOURCE_TIERS` to `{}`. The synthesis in Step 4 will rely on context7 documentation and training knowledge.

### Step 1 — Parallel Exa searches (conditional)

If `SKIP_EXA = true` (set in Step 0), skip this step entirely and proceed to Step 2.

Run all three Bash calls simultaneously (parallel execution). Use `SEARCH_TECH` (from Step 0) in place of `TECH` when building search queries:

**Primary search:**

```bash
best-practices-rag search-exa \
  --query "<PRIMARY_QUERY>" \
  --cutoff-date "<CUTOFF_DATE>" \
  --output-file /tmp/bp_exa_primary.md
```

**Failure-mode search:**

```bash
best-practices-rag search-exa \
  --query "<PRIMARY_QUERY> pitfalls gotchas production issues" \
  --cutoff-date "<CUTOFF_DATE>" \
  --output-file /tmp/bp_exa_failures.md
```

**Authority search** — targets GitHub Issues/Discussions/READMEs where library authors post design rationale and recommended approaches:

```bash
best-practices-rag search-exa \
  --query "<TECH as space-separated names> <core topic from QUERY> recommended approach design decision rationale" \
  --category github \
  --cutoff-date "<CUTOFF_DATE>" \
  --output-file /tmp/bp_exa_authority.md
```

Construct the authority query by combining the TECH names (space-separated, not comma-separated) with the core topic extracted from QUERY, then appending the fixed phrase `recommended approach design decision rationale`. Example for `TECH=fastapi,sqlalchemy` and `QUERY=async session management`: `"fastapi sqlalchemy async session management recommended approach design decision rationale"`.

Each search writes its results as markdown to a file via `--output-file`. After all three complete (regardless of exit code — a non-zero exit means the results file is empty, not that the pipeline should stop):

1. Read(`/tmp/bp_exa_primary.md`) — primary search results
2. Read(`/tmp/bp_exa_failures.md`) — failure-mode results
3. Read(`/tmp/bp_exa_authority.md`) — authority results

The markdown is directly readable — no JSON parsing needed. Collect `SOURCE_URLS` from the `=== RESULT: <url> ===` headers. Retain all content in context for Step 4. If a file is empty, collect zero URLs from it and continue normally.

**URL deduplication:** After reading all three result files, identify URLs appearing in more than one search. Keep only the first occurrence (priority: primary > failure-mode > authority) and discard duplicates. Update SOURCE_URLS to the deduplicated set.

**Source tier tagging:** Classify each collected URL into a quality tier and build `SOURCE_TIERS` (a JSON object mapping URL → tier string):

- `Official` — URLs from known official documentation domains. Common patterns: `docs.*`, `*.readthedocs.io`, framework-owned domains (e.g., `fastapi.tiangolo.com`, `docs.sqlalchemy.org`, `docs.pydantic.dev`, `react.dev`, `nextjs.org/docs`, `vuejs.org/guide`, `angular.dev`).
- `Author` — URLs from the authority search (the third Exa call targeting GitHub). All results from that call are Author-tier by default, unless they also match an Official domain (in which case, prefer Official).
- `Community` — everything else (blog posts, tutorials, Stack Overflow, Medium, dev.to, etc.).

Example `SOURCE_TIERS`: `{"https://docs.sqlalchemy.org/en/20/orm/session.html": "Official", "https://github.com/sqlalchemy/sqlalchemy/discussions/1234": "Author", "https://blog.example.com/sqlalchemy-tips": "Community"}`

### Step 2 — Fetch official documentation via context7

For each library in TECH, call `mcp__context7__resolve-library-id` to get the Context7 library ID, then call `mcp__context7__query-docs` with the resolved ID and a focused topic derived from QUERY.

Apply the following token allocation strategy:

**Library classification:**
- Primary (core frameworks: React, Django, FastAPI, Next.js, Vue, Angular): 60% of available tokens, up to 3,000 tokens per library
- Secondary (tools and utilities: TypeScript, Tailwind, Prisma, ESLint, Vite, Webpack, and similar): 30% of available tokens, up to 1,500 tokens per library

**Execution rules:**
- Process Primary libraries first, then Secondary
- Handle resolution failures gracefully — if a library cannot be resolved, continue with the remaining libraries and note the failure
- Use QUERY and MODE as the topic/focus for each `mcp__context7__query-docs` call to maximize relevance

Retain all retrieved documentation content in this ephemeral context.

### Step 3 — Read synthesis format

Always read `~/.claude/skills/best-practices-rag/references/synthesis-format-research.md` regardless of MODE.

Storing in research format ensures the richer content (architectural rationale, design tradeoffs, in-depth analysis) is available for downstream synthesis. MODE is retained in the input interface for informational context but no longer drives format selection here.

### Step 4 — Synthesize

Synthesize a best-practices document from all gathered sources:
- Primary Exa results
- Failure-mode Exa results
- Context7 documentation from Step 2
- STALE_CONTEXT_BODY (if provided) — treat as historical reference only; do not present stale patterns as current best practices; note version differences and correct any outdated patterns
- STALE_TECHNOLOGIES and VERSION_DELTAS (if provided) — use to focus synthesis on what specifically changed between versions. Prioritize covering migration patterns and breaking changes for the stale technologies.

Include a `SOURCE_TIERS` context block at the top of your synthesis working notes (not in the final output) listing which URLs are Official, Author, or Community. Use this to resolve conflicts per the source-preference rule in the synthesis format.

Follow all rules in the synthesis format file selected in Step 3. The synthesis must:
- Follow the required section structure exactly as defined in the format file
- Incorporate findings from all source content
- Flag any deprecated APIs identified in the context7 documentation
- Label each reference in the References section with its tier (`[Official]`, `[Library Author]`, or `[Community]`) matching the `SOURCE_TIERS` classification from Step 1

If `LANGUAGE_AGNOSTIC` is `true`, apply the language-agnostic synthesis rules from the synthesis format file — use pseudocode for all code examples and avoid language-specific API calls or imports.

### Step 4.5 — Self-review

Re-read the synthesized document before writing. Fix any issues in-place — this is a single pass, not an iterative loop.

1. **References**: For each entry, verify it ends with `[Official]`, `[Library Author]`, or `[Community]`
   matching the SOURCE_TIERS classification from Step 1. If SKIP_EXA was true and no SOURCE_TIERS exist,
   infer tier from URL domain (docs.* or official framework domains → Official; GitHub Issues/Discussions
   → Library Author; everything else → Community).
2. **Core Concepts**: Verify each `###` heading names a problem-domain concept, not a technology feature.
3. **Anti-Patterns**: Verify that each anti-pattern involving subtle runtime behavior, concurrency, or
   resource leaks has BAD/GOOD code blocks. Only anti-patterns with a single obvious API misuse
   (e.g., calling a removed method) may use a brief prose mention instead.
4. **Cross-section de-duplication**: If an anti-pattern is already demonstrated inline within a Core
   Concept (as a tradeoff or edge case with code), do not repeat it in Anti-Patterns & Pitfalls.
   The Anti-Patterns section should contain only standalone anti-patterns not covered by any Core Concept.

### Step 5 — Write output

Write the synthesized document to `OUTPUT_FILE` (the workspace-relative path supplied in the input).

### Step 6 — Store result

Call `best-practices-rag store-result` via Bash. Use `STORE_TECH` (from Step 0) as the `--tech` value — this ensures the gap-filled content is stored as a separate KB node scoped to the uncovered technologies, allowing the synthesizer to retrieve and merge both nodes independently:

```bash
best-practices-rag store-result \
  --tech "<STORE_TECH value>" \
  --query "<QUERY value>" \
  --content-file "<OUTPUT_FILE value>" \
  --source-urls "<SOURCE_URLS from Step 1>" \
  --tech-versions '<TECH_VERSIONS_JSON value>' \
  --source-tiers '<SOURCE_TIERS JSON from Step 1>' \
  [--languages "<LANGUAGES value>"]
```

Omit `--languages` if LANGUAGES was not provided. `--source-tiers` is the JSON object built in Step 1 mapping each URL to its quality tier. Omit `--source-urls` and `--source-tiers` if `SKIP_EXA` was true (no Exa results to store).

Steps 0–6 are complete. Proceed to Step 7 for MODE-selective final synthesis.

### Step 7 — MODE-selective synthesis

Run the query command:

```bash
best-practices-rag query-kb \
  --tech "<TECH value>" \
  --topics "<TOPICS value>" \
  [--languages "<LANGUAGES value>"] \
  --format md
```

The output is a markdown document containing metadata and body content for all KB entries.
Entries are delimited by `=== ENTRY: <name> | STATUS: fresh/stale ===` headers. Each entry's
metadata appears as bullet lines before a `---` separator, followed by the full body content.

Collect all entries with `STATUS: fresh` as FRESH_DOCS. If no fresh entries exist, treat all
entries as candidates regardless of staleness.

**Select synthesis format:**
- If `MODE` is `codegen`, read `~/.claude/skills/best-practices-rag/references/synthesis-format-codegen.md`
- If `MODE` is `research`, read `~/.claude/skills/best-practices-rag/references/synthesis-format-research.md`

The selected format document defines the required sections, target length, and mode-specific rules.

Note: KB documents may have been stored in research format. When MODE is `codegen` and the stored content contains architectural rationale or in-depth analysis, extract the actionable patterns and Critical API Changes from that richer content and reformat according to the codegen format rules. If research-format anti-patterns are prose-only (no BAD/GOOD code blocks), expand them to BAD/GOOD code pairs during synthesis — the codegen format requires code blocks for every anti-pattern entry.

**Critical evaluation:**

Before synthesizing, evaluate the KB content against your own training knowledge. This step is what makes the output valuable — without it, the document is just reformatted search results.

**For MODE=codegen:**

1. Read all FRESH_DOCS bodies.
2. For each pattern or recommendation, classify it:
   - **Novel**: Not in your training data, contradicts your training data, or describes
     an API that changed after your training cutoff. Highest priority for inclusion.
   - **Emphasis-worthy**: In your training data but represents a pattern LLM agents
     frequently get wrong or skip. Include for reinforcement.
   - **Redundant**: Well-covered in training data and agents typically handle correctly.
     Omit unless space permits.
3. Prioritize: Novel > Emphasis-worthy > Redundant.
4. For Critical API Changes: identify every case where the source material shows an API
   that differs from what you would generate from training data alone. Only include APIs
   that production code calls directly — API changes in testing utilities (e.g., pytest-asyncio
   mode settings) or HTTP test clients (e.g., httpx ASGITransport) are not Critical API Changes
   regardless of whether those libraries appear in TECH. Route those to the Testing Pattern section.
5. For Canonical Patterns: select the BEST implementation for each concern — whether
   from source material, your training knowledge, or a combination of both.

**For MODE=research:**

1. Read all FRESH_DOCS bodies.
2. Identify natural conceptual groupings. Group related patterns, anti-patterns, and
   implementation details under concept headings based on the problem domain.
3. For each concept, identify the core design problem it addresses.
4. Where source recommendations differ from your training knowledge, present both
   perspectives with your assessment of which is more appropriate and why.

**Synthesize:**

Merge all `FRESH_DOCS` body fields into a single best-practices document following all rules in the selected format file. The synthesis must:
- Follow the required section structure exactly as defined in the format file
- Incorporate content from all fresh KB bodies, resolving any conflicts by preferring the most complete or recently synthesized entry
- Flag any deprecated APIs or outdated patterns noted in the source bodies
- Apply the classifications from the critical evaluation above to select and prioritize content
- For MODE=codegen: the Critical API Changes section must contain ONLY items classified as Novel. Canonical Patterns should prioritize Emphasis-worthy items. De-duplicate across all sections: if the same API change or pattern appears in more than one section (e.g., Critical API Changes AND Anti-Patterns, or Canonical Patterns AND Anti-Patterns), keep it in the higher-priority section and remove it from the lower one. Priority order: Critical API Changes > Canonical Patterns > Anti-Patterns.
- For MODE=research: use the conceptual groupings from the critical evaluation as the organizing structure for Core Concepts. Generate a Table of Contents from the final heading structure.
- If `LANGUAGE_AGNOSTIC` is `true`, apply the language-agnostic code rules from the synthesis format file. This overrides language-specific code example behavior.

**Self-review:**

Re-read the synthesized document before writing. Check each item against its checklist. This is a single pass, not an iterative loop — fix issues in-place, then proceed to write.

**For MODE=codegen:**

1. **Critical API Changes**: For each entry, verify:
   - The ❌ pattern actually fails, raises a warning, or uses a removed API — not merely
     a style preference or older-but-functional approach.
   - The entry is correctly classified as Novel (differs from what you would generate
     from training data alone). Remove any entry that fails this check.
   - The entry covers a primary framework or library API that production code calls directly.
     API changes in testing utilities (e.g., pytest-asyncio mode settings) or HTTP test clients
     (e.g., httpx ASGITransport) belong in the Testing Pattern section, not Critical API Changes,
     even if those libraries appear in TECH.
2. **Canonical Patterns**: For each pattern, verify:
   - The code compiles/runs as written (correct imports, no undefined references).
   - The version comment on the first line matches the actual APIs used in the block.
3. **Anti-Patterns**: Verify each BAD block demonstrates a mistake an LLM agent would
   plausibly make, not a mistake only a beginner would make. Remove any that don't qualify.
4. **Anti-Patterns**: For each anti-pattern entry, locate the GOOD block immediately following
   the BAD block. If the GOOD block is absent, is prose, or references another section (e.g.,
   "see Canonical Patterns above"), write a self-contained GOOD code block in its place. If you
   cannot write a self-contained GOOD code block, delete the entire anti-pattern entry. "See X
   above" is not a GOOD code block under any circumstances.
5. **References**: For each entry, verify it ends with `[Official]`, `[Library Author]`, or `[Community]`.
   If any label is missing, infer the tier from the URL domain (e.g., `docs.*`, framework-owned domains
   → Official; GitHub Issues/Discussions → Library Author; everything else → Community) and add it.

**For MODE=research:**

1. **Core Concepts**: Verify each `###` heading names a problem-domain concept
   (e.g., "Session Lifecycle Management") not a technology feature
   (e.g., "AsyncSession Configuration").
2. **Table of Contents**: Scan the FULL document for every `##` and `###` heading.
   Rebuild the TOC from scratch to include all headings — do not rely on the TOC
   written during drafting. This is the final TOC that will appear in the output.
3. **Anti-Patterns**: Verify that anti-patterns with obvious failure modes use brief
   mentions rather than full BAD/GOOD blocks.
4. **References**: For each entry, verify it ends with `[Official]`, `[Library Author]`, or `[Community]`.
   Infer from URL domain if tier is not in SOURCE_TIERS context.

**Write output:**

Before writing the synthesized content, prepend YAML frontmatter:

```yaml
---
tech_versions: <TECH_VERSIONS_JSON value from input parameters>
claude_model: <your exact model ID from system prompt, e.g. claude-sonnet-4-6>
synthesized_at: <current UTC timestamp in ISO 8601, e.g. 2026-03-19T14:30:00Z>
---
```

The frontmatter goes above the existing `# Title` line. The rest of the document (title, metadata block, sections) remains unchanged.

Write the synthesized document to `OUTPUT_FILE` (the workspace-relative path supplied in the input block), overwriting the gap-fill document written in Step 5.

**EXTRA_TECHS computation:**

If `COVERED_TECHS` and `ALL_QUERIED_TECHS` were provided in the input:
- Compute `EXTRA_TECHS` = tech names in `COVERED_TECHS` that are NOT in `ALL_QUERIED_TECHS`
- Include `EXTRA_TECHS` in the completion signal below (comma-separated, or empty string if none)

If neither field was provided, set `EXTRA_TECHS` to empty string.

Also compute `KB_STORED`:
- `true` if Steps 0–6 ran and store-result was called
- `false` if this was a cache-hit invocation (Steps 0–6 were skipped)

### Step 8 — Return completion signal

Return ONLY the following structured signal — do not include synthesized document content, status messages, step headings, or any other text before or after the signal. The entire agent response must be exactly this string (substituting actual values):

```text
BP_PIPELINE_COMPLETE. Output: <OUTPUT_FILE value>. Extra: <EXTRA_TECHS comma-separated or empty>. KB_Stored: <true|false>
```

Example (gap path with extra techs): `BP_PIPELINE_COMPLETE. Output: .best-practices/fastapi-sqlalchemy-async-session-management-codegen.md. Extra: asyncpg. KB_Stored: true`

Example (cache hit, no extra): `BP_PIPELINE_COMPLETE. Output: .best-practices/fastapi-async-codegen.md. Extra: . KB_Stored: false`