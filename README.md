# best-practices-rag

A Claude Code skill pipeline for technology best practices via Neo4j knowledge graph.
Works with any project language — Go, Rust, Python, TypeScript, etc.

## Quick Start

### New project (standalone Neo4j via Docker)

```bash
# Install globally (works with any project language)
uv tool install git+https://github.com/mmcclatchy/best-practices-rag.git
# or: pipx install git+https://github.com/mmcclatchy/best-practices-rag.git

# One-command setup: creates .env, installs .claude/ files, starts Neo4j, validates
best-practices-rag init
```

To set a specific Neo4j password instead of a generated one:

```bash
best-practices-rag init --password mysecretpassword
```

### Existing Neo4j (already in your docker-compose or remote)

```bash
pipx install git+https://github.com/mmcclatchy/best-practices-rag.git
best-practices-rag install         # copies .claude/ files into this project
cp .env.example .env               # then set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD
best-practices-rag setup-schema    # applies schema to your existing Neo4j
best-practices-rag check
```

If you need to add an Exa API key after setup, edit `.env` and add:

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
- Docker (for Neo4j — only required for standalone path)
- Claude Code CLI
- Exa API key (optional, enables web search gap-fill)

## How It Works

1. `/bp` queries the Neo4j knowledge graph for existing best practices
2. If results are stale or missing, it searches the web via Exa API
3. Results are synthesized and stored in Neo4j for future queries
4. The knowledge graph grows over time, reducing API calls

## All Commands

```bash
best-practices-rag init           # one-command setup (standalone Docker path)
best-practices-rag install        # copy .claude/ files only
best-practices-rag setup-db       # start Neo4j via Docker and apply schema
best-practices-rag setup-schema   # apply schema to existing Neo4j (no Docker required)
best-practices-rag check          # validate installation
best-practices-rag query-kb       # query knowledge base (used by /bp)
best-practices-rag search-exa     # search Exa (used by gap-fill agent)
best-practices-rag store-result   # store synthesized result to Neo4j
best-practices-rag uninstall      # remove installed .claude/ files
```

## Version

v0.1.3
