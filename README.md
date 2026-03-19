# best-practices-rag

A Claude Code skill pipeline for technology best practices via Neo4j knowledge graph.
Works with any project language — Go, Rust, Python, TypeScript, etc.

## Quick Start

### Standalone Neo4j via Docker

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

- Python 3.10+ (for the CLI — not required in your project)
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

## Version

v0.1.5
