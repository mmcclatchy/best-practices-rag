from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from best_practices_rag.tui import TuiAdapter

from best_practices_rag.templates.bp_command import generate_bp_command
from best_practices_rag.templates.bp_pipeline_agent import generate_bp_pipeline_agent
from best_practices_rag.tui import AgentSpec, BpMode, CommandSpec, ModelType


def build_specs(adapter: TuiAdapter) -> tuple[list[AgentSpec], list[CommandSpec]]:
    bp_invocation = adapter.render_command_invocation(BpMode.CODEGEN.command_name, "")
    bpr_invocation = adapter.render_command_invocation(BpMode.RESEARCH.command_name, "")
    agents: list[AgentSpec] = [
        AgentSpec(
            name="bp-pipeline",
            description=f"Full gap-fill and synthesis pipeline for best-practices-rag. Delegate to this agent when {bp_invocation} or {bpr_invocation} detects a knowledge-base gap (full or partial) or on a cache hit that still needs synthesis. Runs Exa searches, context7 documentation fetches, stores the gap result to Neo4j, then queries the KB and synthesizes the final MODE-appropriate output document. Returns BP_PIPELINE_COMPLETE signal with the output file path.",
            model_type=ModelType.TASK,
            tools=[
                "Bash",
                "mcp__context7__resolve-library-id",
                "mcp__context7__query-docs",
                "Read",
                "Write",
            ],
            body=generate_bp_pipeline_agent(adapter),
            color="green",
        ),
    ]

    commands: list[CommandSpec] = [
        CommandSpec(
            name=mode.command_name,
            description=mode.description,
            body=generate_bp_command(adapter, mode),
        )
        for mode in BpMode
    ]

    return agents, commands
