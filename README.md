# best-practices-rag

A Claude Code skill pipeline for technology best practices via Neo4j knowledge graph.
Works with any project language — Go, Rust, Python, TypeScript, etc.

## Quick Start

### Standalone Neo4j via Docker

**Install Docker** (required for this path):

- **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
  or via Homebrew: `brew install --cask docker`
- **Linux**: [Install Docker Engine](https://docs.docker.com/engine/install/) for your distro,
  then install the [Compose plugin](https://docs.docker.com/compose/install/linux/)
- **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
  — see [Windows setup notes](#windows) before continuing

```bash
# Install globally — uv manages Python automatically, no separate Python install needed
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
# or: pipx install git+https://github.com/mmcclatchy/best-practices-rag.git

# One-command global setup: installs ~/.claude/ files, starts Neo4j, applies schema
best-practices-rag setup
```

To set a specific Neo4j password instead of a generated one:

```bash
best-practices-rag setup --password mysecretpassword
```

### Existing Neo4j (already running or remote)

```bash
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
best-practices-rag setup --neo4j-uri bolt://your-server:7687
```

If you need to add an Exa API key after setup, edit `~/.config/best-practices-rag/.env` and add:

```bash
EXA_API_KEY=your-exa-api-key-here
```

## Usage

Once installed, use `/bp` in Claude Code for synthesized best practices:

```text
/bp fastapi sqlalchemy async
/bp react typescript state management
/bp docker kubernetes deployment patterns
```

Use `/bpr` for research mode — deeper architectural analysis and design tradeoffs.

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages Python automatically (no separate Python install needed)
- [Docker](https://www.docker.com/) — required for the standalone Neo4j setup path
- Claude Code CLI
- Exa API key (optional, enables web search gap-fill)

## How It Works

1. `/bp` queries the Neo4j knowledge graph for existing best practices
2. If results are stale or missing, it searches the web via Exa API
3. Results are synthesized and stored in Neo4j for future queries
4. The knowledge graph grows over time, reducing API calls

## All Commands

```bash
best-practices-rag setup          # global one-command setup
best-practices-rag setup-schema   # apply schema to existing Neo4j (no Docker required)
best-practices-rag check          # validate global installation (~/.claude/)
best-practices-rag query-kb       # query knowledge base (used by /bp)
best-practices-rag search-exa     # search Exa (used by gap-fill agent)
best-practices-rag store-result   # store synthesized result to Neo4j
best-practices-rag uninstall      # remove installed ~/.claude/ files
best-practices-rag version        # show installed version
best-practices-rag update         # upgrade to the latest release
```

## Windows

> **Note:** Windows support in Claude Code is evolving. If anything below seems out of date,
> refer to the [official Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code/setup).

Claude Code on Windows uses Git Bash internally, regardless of whether you launch it from
PowerShell, CMD, or Git Bash directly. [Git for Windows](https://git-scm.com/downloads/win)
must be installed first. WSL2 is optional — it is only required for Claude Code's `/sandbox`
feature.

**Install `uv` via the Windows installer** (run in PowerShell or CMD, not Git Bash):

```powershell
winget install astral-sh.uv
# or
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Using the Linux curl script inside Git Bash installs a Linux build of `uv` that won't integrate
with the Windows PATH, so Claude Code won't be able to find `best-practices-rag`.

Once `uv` is installed, continue from Git Bash, PowerShell, or CMD:

```bash
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
best-practices-rag setup
```

`~` in Git Bash resolves to `C:\Users\<username>` — the same home directory Python uses on
Windows — so `~/.claude/` and `~/.config/best-practices-rag/` align correctly between the CLI
and Claude Code.

**WSL2 users:** Install `uv` and `best-practices-rag` from inside the WSL2 terminal using the
Linux instructions. Docker Desktop automatically exposes the Docker socket to WSL2.

## Version

v0.1.5
