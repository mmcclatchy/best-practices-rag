# best-practices-rag

A Claude Code skill pipeline for technology best practices via Neo4j knowledge graph.
Works with any project language — Go, Rust, Python, TypeScript, etc.

---

## What is best-practices-rag?

Getting up-to-date API references is a solved problem — tools like [Context7](https://context7.com) pull current library docs on demand. What remains harder is getting Claude to write code the *right way*: following the patterns a library's authors intended, avoiding common pitfalls, structuring code the way experienced practitioners in that ecosystem actually do it.

**best-practices-rag gives Claude a curated knowledge graph of coding patterns and best practices sourced from official documentation, authoritative community resources, and real-world guidance.**

When you run `/bp fastapi dependency injection`, Claude queries that knowledge graph first. If a current, high-quality answer is already stored, it is returned instantly — no web search, zero API cost. Claude uses the retrieved patterns directly in its code generation, giving it concrete examples to emulate, anti-patterns to avoid, and the idiomatic conventions that reduce bugs and keep code maintainable.

If the knowledge graph has no answer (or it has gone stale), the tool searches the web via [Exa](https://exa.ai), synthesizes the findings into a structured best-practices document, and stores it back in Neo4j. **Every Exa search is an investment: subsequent queries on the same topic are served from the local graph at no cost.**

Exa includes **1,000 free requests per month** (no credit card required) — enough for roughly 333 uncached gap-fills before any cost kicks in. Beyond the free tier, each gap-fill makes 3 neural searches at ~$0.024 total. See [Exa pricing](https://exa.ai/pricing) for details.

### Benefits

- **Idiomatic code**
  - Claude emulates patterns from authoritative sources rather than inferring from training data, producing code that follows how technologies are meant to be used
- **Fewer bugs**
  - Explicit anti-patterns and common pitfalls are part of the stored knowledge, giving Claude specific things to avoid during generation
- **Generous free tier**
  - Exa provides 1,000 free requests/month (~333 gap-fills) with no credit card required
  - The graph grows over time so the same topics are never searched twice
- **Two modes**
  - `/bp` for concise, implementation-focused patterns
  - `/bpr` for deep architectural analysis and design tradeoff research
- **Language agnostic**
  - One global install serves every project on your machine regardless of language or framework
- **Works offline for cached topics**
  - Once a best practice is stored, Neo4j serves it without any network call

---

## Quick Start

Choose the path that matches your Neo4j setup.

---

### Option 1: Standalone Neo4j via Docker

**Prerequisites — install Docker for your OS:**

- **macOS:** [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) or `brew install --cask docker`
- **Linux:** [Docker Engine](https://docs.docker.com/engine/install/) + [Compose plugin](https://docs.docker.com/compose/install/linux/)
- **Windows:** [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) — see [Windows setup notes](#windows) before continuing

```bash
# uv manages Python automatically — no separate Python install needed
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
# or: pipx install git+https://github.com/mmcclatchy/best-practices-rag.git

# Installs ~/.claude/ skill files, starts Neo4j, and applies schema
best-practices-rag setup
```

To set a specific Neo4j password instead of an auto-generated one:

```bash
best-practices-rag setup --password mysecretpassword
```

---

### Option 2: Existing Neo4j (already running or remote)

```bash
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
best-practices-rag setup --neo4j-uri bolt://your-server:7687
```

---

### Setup with Exa API key

```bash
best-practices-rag setup --exa-api-key your-exa-api-key-here
```

Get a free Exa API key at [exa.ai](https://exa.ai/) (1,000 free requests/month).

---

### Option 3: OpenCode

best-practices-rag supports [OpenCode](https://opencode.ai) in addition to Claude Code.
Use `--tui` to control which tool(s) receive the installed agents and commands:

```bash
# Install for OpenCode only
best-practices-rag setup --tui opencode

# Install for both Claude Code and OpenCode
best-practices-rag setup --tui both

# Auto-detect installed TUIs (default — installs for whichever is found)
best-practices-rag setup
```

The `--tui` flag is available on `setup`, `check`, `uninstall`, and `update`.

Skills/reference files are always installed to `~/.claude/skills/` — OpenCode reads
them from that location via its built-in compat shim, so no duplication is needed.

---

## Usage

Once installed, use `/bp` in Claude Code or OpenCode for synthesized best practices:

```text
/bp fastapi sqlalchemy async
/bp react typescript state management
/bp docker kubernetes deployment patterns
```

Use `/bpr` for research mode — deeper architectural analysis and design tradeoffs.

---

### Force-refreshing a cached document

Cached results are checked for staleness automatically, but you can force a fresh Exa search at any time with the `--force-refresh` flag:

```text
/bp --force-refresh fastapi sqlalchemy async
/bp fastapi sqlalchemy async --force-refresh
```

This skips the local cache entirely, fetches new content from Exa, and updates the stored document. Use this when you know something has changed and want the latest guidance without waiting for the automatic staleness check.

> **Note:** `--force-refresh` triggers an Exa web search (~$0.024, or free within the 1,000 requests/month free tier).

---

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages Python automatically (no separate Python install needed)
- [Docker](https://www.docker.com/) — required for the standalone Neo4j setup path
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [Exa API key](https://exa.ai/) — required for gap-fill web searches. Includes **1,000 free requests/month** (~333 gap-fills, no credit card required). Beyond the free tier: ~$0.024 per uncached gap-fill. Results are cached in Neo4j so repeated topics cost nothing.

---

## How It Works

1. `/bp` or `/bpr` queries the Neo4j knowledge graph for stored best practices
2. Fresh, matching results are returned immediately — no network call, no cost
3. If results are missing or stale, the tool searches the web via Exa and synthesizes a structured best-practices document
4. The synthesized document is stored in Neo4j — future queries on the same topic are instant and free

---

## All Commands

```bash
best-practices-rag setup [--tui auto|claude|opencode|both]   # global one-command setup
best-practices-rag setup-schema                              # apply schema to existing Neo4j (no Docker required)
best-practices-rag check [--tui auto|claude|opencode|both]   # validate installed files
best-practices-rag query-kb                                  # query knowledge base (used by /bp)
best-practices-rag search-exa                                # search Exa (used by gap-fill agent)
best-practices-rag store-result                              # store synthesized result to Neo4j
best-practices-rag uninstall [--tui auto|claude|opencode|both]  # remove installed files
best-practices-rag version                                   # show installed version
best-practices-rag update [--tui auto|claude|opencode|both]  # upgrade to the latest release
```

---

## Windows

> **Note:** Windows support in Claude Code is evolving. If anything below seems out of date,
> refer to the [official Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code/setup).

Claude Code uses Git Bash internally on Windows, regardless of whether you launch it from PowerShell, CMD, or Git Bash directly. [Git for Windows](https://git-scm.com/downloads/win) must be installed first. WSL2 is optional — it is only required for Claude Code's `/sandbox` feature.

### Git Bash / PowerShell / CMD

Install `uv` via the **Windows installer** (run in PowerShell or CMD, not Git Bash — the Linux curl script installs the wrong build and Claude Code won't find `best-practices-rag`):

```powershell
winget install astral-sh.uv
# or
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then from Git Bash, PowerShell, or CMD:

```bash
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
best-practices-rag setup
```

`~` in Git Bash resolves to `C:\Users\<username>` — the same home directory Python uses on Windows — so `~/.claude/` and `~/.config/best-practices-rag/` align correctly between the CLI and Claude Code.

### WSL2

Install `uv` and `best-practices-rag` from inside the WSL2 terminal using the Linux instructions above. Docker Desktop automatically exposes the Docker socket to WSL2.

---

## Version

v0.2.2
