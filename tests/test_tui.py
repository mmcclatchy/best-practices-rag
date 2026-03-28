"""Tests for best_practices_rag/tui.py — TUI adapter pattern."""

import json
from pathlib import Path

import pytest

from best_practices_rag.tui import (
    AgentSpec,
    ClaudeCodeAdapter,
    CommandSpec,
    OpenCodeAdapter,
    TuiKind,
    detect_tuis,
    get_adapter,
    parse_claude_agent,
    parse_claude_command,
    resolve_tui_targets,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestAgentSpec:
    def test_frozen(self) -> None:
        spec = AgentSpec(
            name="test",
            description="desc",
            model="sonnet",
            tools=["Bash"],
            body="body",
        )
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "changed"  # type: ignore[misc]

    def test_color_default_none(self) -> None:
        spec = AgentSpec(name="x", description="d", model="sonnet", tools=[], body="b")
        assert spec.color is None


class TestCommandSpec:
    def test_frozen(self) -> None:
        spec = CommandSpec(name="cmd", description="desc", body="body")
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapter:
    def test_install_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = ClaudeCodeAdapter()
        assert adapter.install_root() == tmp_path / ".claude"

    def test_agents_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ClaudeCodeAdapter().agents_dir() == tmp_path / ".claude" / "agents"

    def test_commands_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ClaudeCodeAdapter().commands_dir() == tmp_path / ".claude" / "commands"

    def test_model_name_passthrough(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.model_name("sonnet") == "sonnet"
        assert adapter.model_name("opus") == "opus"

    def test_render_agent_frontmatter(self) -> None:
        spec = AgentSpec(
            name="my-agent",
            description="Does things",
            model="sonnet",
            tools=["Bash", "Read"],
            body="# Body\n\nContent here.",
            color="green",
        )
        adapter = ClaudeCodeAdapter()
        result = adapter.render_agent(spec)
        assert result.startswith("---\n")
        assert "name: my-agent" in result
        assert "description: Does things" in result
        assert "model: sonnet" in result
        assert "color: green" in result
        assert "tools: Bash, Read" in result
        assert "# Body" in result

    def test_render_agent_no_color(self) -> None:
        spec = AgentSpec(
            name="no-color",
            description="x",
            model="haiku",
            tools=[],
            body="body",
        )
        result = ClaudeCodeAdapter().render_agent(spec)
        assert "color:" not in result

    def test_render_command_body_passthrough(self) -> None:
        spec = CommandSpec(name="bp", description="Search", body="# Title\n\nbody content")
        assert ClaudeCodeAdapter().render_command(spec) == spec.body

    def test_write_all_creates_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = ClaudeCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="body")]
        commands = [CommandSpec(name="bp", description="Search", body="bp body")]

        written = adapter.write_all(agents, commands)

        assert (tmp_path / ".claude" / "agents" / "bp-pipeline.md").exists()
        assert (tmp_path / ".claude" / "commands" / "bp.md").exists()
        assert len(written) == 2

    def test_write_all_agent_has_frontmatter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = ClaudeCodeAdapter()
        agents = [AgentSpec(name="agent", description="desc", model="sonnet", tools=["Bash"], body="body")]
        adapter.write_all(agents, [])

        content = (tmp_path / ".claude" / "agents" / "agent.md").read_text()
        assert content.startswith("---")
        assert "name: agent" in content

    def test_installed_file_relpaths(self) -> None:
        adapter = ClaudeCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="b")]
        commands = [CommandSpec(name="bp", description="d", body="b")]
        relpaths = adapter.installed_file_relpaths(agents, commands)
        assert "agents/bp-pipeline.md" in relpaths
        assert "commands/bp.md" in relpaths


# ---------------------------------------------------------------------------
# OpenCodeAdapter
# ---------------------------------------------------------------------------


class TestOpenCodeAdapter:
    def test_install_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert OpenCodeAdapter().install_root() == tmp_path / ".config" / "opencode"

    def test_model_name_mapping(self) -> None:
        adapter = OpenCodeAdapter()
        assert adapter.model_name("sonnet") == "anthropic/claude-sonnet-4-6"
        assert adapter.model_name("opus") == "anthropic/claude-opus-4-6"
        assert adapter.model_name("haiku") == "anthropic/claude-haiku-4-5"

    def test_model_name_fallback(self) -> None:
        assert OpenCodeAdapter().model_name("unknown") == "anthropic/claude-unknown"

    def test_render_agent_body_only(self) -> None:
        spec = AgentSpec(name="x", description="d", model="sonnet", tools=[], body="# Title\nContent")
        assert OpenCodeAdapter().render_agent(spec) == "# Title\nContent"

    def test_render_command_body_only(self) -> None:
        spec = CommandSpec(name="bp", description="d", body="# BP\n\nWorkflow")
        assert OpenCodeAdapter().render_command(spec) == "# BP\n\nWorkflow"

    def test_write_all_creates_prompts_and_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = OpenCodeAdapter()
        agents = [
            AgentSpec(name="bp-pipeline", description="Pipeline", model="sonnet", tools=["Bash", "Read"], body="body")
        ]
        commands = [CommandSpec(name="bp", description="Search", body="cmd body")]

        written = adapter.write_all(agents, commands)

        prompts_dir = tmp_path / ".config" / "opencode" / "prompts"
        assert (prompts_dir / "bp-pipeline.md").exists()
        assert (prompts_dir / "bp.md").exists()

        json_path = tmp_path / ".config" / "opencode" / "opencode.json"
        assert json_path.exists()
        assert len(written) == 3  # 2 prompt files + opencode.json

    def test_write_all_json_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = OpenCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="Pipeline", model="sonnet", tools=["Bash"], body="b")]
        commands = [CommandSpec(name="bp", description="Search", body="c")]
        adapter.write_all(agents, commands)

        config = json.loads(
            (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
        )
        assert config["$schema"] == "https://opencode.ai/config.json"

        agent = config["agent"]["bp-pipeline"]
        assert agent["mode"] == "subagent"
        assert agent["hidden"] is True
        assert agent["model"] == "anthropic/claude-sonnet-4-6"
        assert agent["prompt"] == "{file:prompts/bp-pipeline.md}"
        assert agent["tools"]["bash"] is True

        cmd = config["command"]["bp"]
        assert cmd["description"] == "Search"
        assert cmd["template"] == "{file:prompts/bp.md}"

    def test_write_all_merges_existing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        opencode_dir = tmp_path / ".config" / "opencode"
        opencode_dir.mkdir(parents=True)
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "agent": {"user-agent": {"mode": "primary", "model": "anthropic/claude-opus-4-6"}},
            "command": {"user-cmd": {"template": "user template"}},
            "mcp": {"my-server": {"type": "local"}},
        }
        (opencode_dir / "opencode.json").write_text(json.dumps(existing))

        adapter = OpenCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="b")]
        commands = [CommandSpec(name="bp", description="d", body="b")]
        adapter.write_all(agents, commands)

        config = json.loads((opencode_dir / "opencode.json").read_text())
        # User's existing entries preserved
        assert "user-agent" in config["agent"]
        assert "user-cmd" in config["command"]
        assert "my-server" in config["mcp"]
        # Our entries added
        assert "bp-pipeline" in config["agent"]
        assert "bp" in config["command"]

    def test_write_all_drops_mcp_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = OpenCodeAdapter()
        agents = [
            AgentSpec(
                name="x",
                description="d",
                model="sonnet",
                tools=["Bash", "mcp__context7__query-docs", "Read"],
                body="b",
            )
        ]
        adapter.write_all(agents, [])

        config = json.loads(
            (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
        )
        tools = config["agent"]["x"]["tools"]
        assert "bash" in tools
        assert "read" in tools
        assert not any("mcp" in k for k in tools)

    def test_installed_file_relpaths(self) -> None:
        adapter = OpenCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="b")]
        commands = [CommandSpec(name="bp", description="d", body="b")]
        relpaths = adapter.installed_file_relpaths(agents, commands)
        assert "prompts/bp-pipeline.md" in relpaths
        assert "prompts/bp.md" in relpaths
        assert "opencode.json" in relpaths

    def test_remove_entries_cleans_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        opencode_dir = tmp_path / ".config" / "opencode"
        opencode_dir.mkdir(parents=True)
        config = {
            "agent": {
                "bp-pipeline": {"mode": "subagent"},
                "user-agent": {"mode": "primary"},
            },
            "command": {
                "bp": {"template": "x"},
                "user-cmd": {"template": "y"},
            },
        }
        (opencode_dir / "opencode.json").write_text(json.dumps(config))

        adapter = OpenCodeAdapter()
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="b")]
        commands = [CommandSpec(name="bp", description="d", body="b")]
        adapter.remove_entries(agents, commands)

        result = json.loads((opencode_dir / "opencode.json").read_text())
        assert "bp-pipeline" not in result["agent"]
        assert "user-agent" in result["agent"]
        assert "bp" not in result["command"]
        assert "user-cmd" in result["command"]

    def test_remove_entries_no_json_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = OpenCodeAdapter()
        # Should not raise even if opencode.json doesn't exist
        agents = [AgentSpec(name="bp-pipeline", description="d", model="sonnet", tools=[], body="b")]
        adapter.remove_entries(agents, [])


# ---------------------------------------------------------------------------
# parse_claude_agent
# ---------------------------------------------------------------------------


class TestParseClaudeAgent:
    _AGENT_FILE = """\
---
name: bp-pipeline
description: Full gap-fill pipeline
tools: Bash, mcp__context7__query-docs, Read, Write
model: sonnet
color: green
---

# bp-pipeline

Body content here.
"""

    def test_parses_name(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert spec.name == "bp-pipeline"

    def test_parses_description(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert spec.description == "Full gap-fill pipeline"

    def test_parses_model(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert spec.model == "sonnet"

    def test_parses_color(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert spec.color == "green"

    def test_parses_tools_list(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert "Bash" in spec.tools
        assert "mcp__context7__query-docs" in spec.tools
        assert "Read" in spec.tools
        assert "Write" in spec.tools

    def test_parses_body(self) -> None:
        spec = parse_claude_agent(self._AGENT_FILE)
        assert "# bp-pipeline" in spec.body
        assert "Body content here." in spec.body

    def test_no_color_yields_none(self) -> None:
        text = "---\nname: x\ndescription: d\ntools: Bash\nmodel: sonnet\n---\nbody"
        spec = parse_claude_agent(text)
        assert spec.color is None

    def test_missing_frontmatter_raises(self) -> None:
        with pytest.raises(ValueError, match="frontmatter"):
            parse_claude_agent("# No frontmatter\n\nBody here.")

    def test_unclosed_frontmatter_raises(self) -> None:
        with pytest.raises(ValueError, match="unclosed"):
            parse_claude_agent("---\nname: x\ndescription: d\n")


# ---------------------------------------------------------------------------
# parse_claude_command
# ---------------------------------------------------------------------------


class TestParseClaudeCommand:
    def test_extracts_h1_as_description(self) -> None:
        text = "# Best Practices Research\n\nWorkflow steps here."
        spec = parse_claude_command(text, "bp")
        assert spec.name == "bp"
        assert spec.description == "Best Practices Research"

    def test_body_is_full_text_when_no_frontmatter(self) -> None:
        text = "# Title\n\nContent"
        spec = parse_claude_command(text, "bp")
        assert spec.body == text

    def test_strips_frontmatter(self) -> None:
        text = "---\nallowed-tools: Bash\n---\n# Title\n\nContent"
        spec = parse_claude_command(text, "bp")
        assert "---" not in spec.body
        assert "allowed-tools" not in spec.body
        assert "# Title" in spec.body

    def test_fallback_description_is_name(self) -> None:
        text = "No heading here, just prose."
        spec = parse_claude_command(text, "my-cmd")
        assert spec.description == "my-cmd"

    def test_description_research_mode(self) -> None:
        text = "# Best Practices Research — Research Mode\n\nWorkflow"
        spec = parse_claude_command(text, "bpr")
        assert spec.description == "Best Practices Research — Research Mode"


# ---------------------------------------------------------------------------
# get_adapter / resolve_tui_targets / detect_tuis
# ---------------------------------------------------------------------------


class TestGetAdapter:
    def test_returns_claude_adapter(self) -> None:
        assert isinstance(get_adapter(TuiKind.CLAUDE), ClaudeCodeAdapter)

    def test_returns_opencode_adapter(self) -> None:
        assert isinstance(get_adapter(TuiKind.OPENCODE), OpenCodeAdapter)


class TestResolveTuiTargets:
    def test_both(self) -> None:
        result = resolve_tui_targets("both")
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE in result

    def test_claude_only(self) -> None:
        result = resolve_tui_targets("claude")
        assert result == [TuiKind.CLAUDE]

    def test_opencode_only(self) -> None:
        result = resolve_tui_targets("opencode")
        assert result == [TuiKind.OPENCODE]

    def test_auto_falls_back_to_claude_when_none_detected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = resolve_tui_targets("auto")
        assert result == [TuiKind.CLAUDE]

    def test_auto_returns_detected_tuis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "best_practices_rag.tui.detect_tuis",
            lambda: [TuiKind.CLAUDE, TuiKind.OPENCODE],
        )
        result = resolve_tui_targets("auto")
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE in result


class TestDetectTuis:
    def test_detects_claude(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            "best_practices_rag.tui.shutil.which",
            lambda x: "/usr/bin/claude" if x == "claude" else None,
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = detect_tuis()
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE not in result

    def test_detects_opencode_via_which(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            "best_practices_rag.tui.shutil.which",
            lambda x: "/usr/bin/opencode" if x == "opencode" else None,
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = detect_tuis()
        assert TuiKind.OPENCODE in result

    def test_detects_opencode_via_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr("best_practices_rag.tui.shutil.which", lambda _: None)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        opencode_bin = tmp_path / ".opencode" / "bin"
        opencode_bin.mkdir(parents=True)
        (opencode_bin / "opencode").write_text("")  # create the binary file

        result = detect_tuis()
        assert TuiKind.OPENCODE in result

    def test_detects_both(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            "best_practices_rag.tui.shutil.which",
            lambda x: f"/usr/bin/{x}" if x in ("claude", "opencode") else None,
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = detect_tuis()
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE in result

    def test_detects_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr("best_practices_rag.tui.shutil.which", lambda _: None)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = detect_tuis()
        assert result == []
