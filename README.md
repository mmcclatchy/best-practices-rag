# best-practices-rag

A Claude Code skill pipeline for technology best practices via Neo4j knowledge graph.

## Quick Start

```bash
# Install the package from GitHub
uv add git+https://github.com/mmcclatchy/best-practices-rag.git

# Copy agents, commands, and scripts to your .claude/ directory
uv run best-practices-rag install

# Start Neo4j via Docker and apply the schema
uv run best-practices-rag setup-db

# Edit .env with your Neo4J_PASSWORD (and optionally EXA_API_KEY)
cp .env.example .env
# edit .env

# Validate everything is working
uv run best-practices-rag check
```

## Usage

Once installed, use the `/bp` command in Claude Code:

```text
/bp fastapi sqlalchemy async
/bp react typescript state management
/bp docker kubernetes deployment patterns
```

Use `/bpr` for research mode (returns raw sources instead of synthesized output).

## Requirements

- Python 3.10+ (3.13+ recommended)
- Docker (for Neo4j)
- Claude Code CLI
- Exa API key (optional, for web search gap-fill)

## How It Works

1. `/bp` queries the Neo4j knowledge graph for existing best practices
2. If results are stale or missing, it searches the web via Exa API
3. Results are synthesized and stored in Neo4j for future queries
4. The knowledge graph grows over time, reducing API calls

## Version

v0.0.3
