"""Tests for template generation functions."""

from pathlib import Path

from best_practices_rag.templates.bp_command import generate_bp_command
from best_practices_rag.templates.bp_pipeline_agent import generate_bp_pipeline_agent
from best_practices_rag.tui import BpMode, ClaudeCodeAdapter, CodexAdapter, ModelConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _make_claude_adapter() -> ClaudeCodeAdapter:
    config = ModelConfig(reasoning_model="opus", task_model="sonnet")
    return ClaudeCodeAdapter(config)


class TestGenerateBpCommand:
    def test_codegen_matches_fixture(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        expected = (FIXTURES / "bp_claude_expected.md").read_text(encoding="utf-8")
        assert result == expected

    def test_research_matches_fixture(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.RESEARCH)
        expected = (FIXTURES / "bpr_claude_expected.md").read_text(encoding="utf-8")
        assert result == expected

    def test_codegen_contains_tilde_reference_paths(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        assert "~/.config/best-practices-rag/references/tech-versions.md" in result

    def test_research_contains_tilde_reference_paths(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.RESEARCH)
        assert "~/.config/best-practices-rag/references/tech-versions.md" in result

    def test_codegen_no_dot_slash_paths(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        assert "./.claude/" not in result

    def test_research_no_dot_slash_paths(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.RESEARCH)
        assert "./.claude/" not in result

    def test_codegen_contains_pipeline_invocation(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        assert "Task(bp-pipeline):" in result
        assert "MODE: codegen" in result

    def test_research_contains_pipeline_invocation(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_command(adapter, BpMode.RESEARCH)
        assert "Task(bp-pipeline):" in result
        assert "MODE: research" in result


class TestGenerateBpPipelineAgent:
    def test_matches_fixture(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        expected = (FIXTURES / "bp_pipeline_claude_expected.md").read_text(
            encoding="utf-8"
        )
        assert result == expected

    def test_contains_tilde_synthesis_research_path(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert (
            "~/.config/best-practices-rag/references/synthesis-format-research.md"
            in result
        )

    def test_contains_tilde_synthesis_codegen_path(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert (
            "~/.config/best-practices-rag/references/synthesis-format-codegen.md"
            in result
        )

    def test_no_dot_slash_claude_paths(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert "./.claude/" not in result

    def test_contains_tech_versions_path(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert "~/.config/best-practices-rag/references/" in result

    def test_starts_with_bp_pipeline_heading(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert result.startswith("# bp-pipeline")

    def test_contains_bp_pipeline_complete_signal(self) -> None:
        adapter = _make_claude_adapter()
        result = generate_bp_pipeline_agent(adapter)
        assert "BP_PIPELINE_COMPLETE" in result


def _make_codex_adapter() -> CodexAdapter:
    config = ModelConfig(reasoning_model="o4-mini", task_model="o4-mini")
    return CodexAdapter(config)


class TestCodexAdapterTemplates:
    def test_generate_bp_command_codex_contains_invoke_skill(self) -> None:
        adapter = _make_codex_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        assert "Invoke the 'bp-pipeline' skill" in result

    def test_generate_bp_command_codex_no_task_block(self) -> None:
        adapter = _make_codex_adapter()
        result = generate_bp_command(adapter, BpMode.CODEGEN)
        assert "Task(bp-pipeline):" not in result
