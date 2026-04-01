"""Agent and command definitions - TUI-agnostic metadata."""

from best_practices_rag.tui import AgentSpec, CommandSpec, ModelType


AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="bp-pipeline",
        description="Full gap-fill and synthesis pipeline for best-practices-rag. Invoke via Task(bp-pipeline) when /bp or /bpr detects a knowledge-base gap (full or partial) or on a cache hit that still needs synthesis. Runs Exa searches, context7 documentation fetches, stores the gap result to Neo4j, then queries the KB and synthesizes the final MODE-appropriate output document. Returns BP_PIPELINE_COMPLETE signal with the output file path.",
        model_type=ModelType.TASK,
        tools=[
            "Bash",
            "mcp__context7__resolve-library-id",
            "mcp__context7__query-docs",
            "Read",
            "Write",
        ],
        body="bp-pipeline.md",
        color="green",
    ),
]

COMMANDS: list[CommandSpec] = [
    CommandSpec(
        name="bp",
        description="Query the best-practices knowledge base for technology-specific guidance",
        body="bp.md",
    ),
    CommandSpec(
        name="bpr",
        description="Force gap-fill and resynthesis",
        body="bpr.md",
    ),
]
