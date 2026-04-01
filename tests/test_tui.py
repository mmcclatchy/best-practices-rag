"""Tests for best_practices_rag/tui.py — TUI adapter pattern."""

import json
from pathlib import Path

import pytest

from best_practices_rag.tui import (
    AgentSpec,
    ClaudeCodeAdapter,
    CommandSpec,
    ModelConfig,
    ModelType,
    OpenCodeAdapter,
    TuiKind,
    detect_tuis,
    get_adapter,
    register_adapter,
    resolve_tui_targets,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestAgentSpec:
    def test_create_with_model_type(self) -> None:
        spec = AgentSpec(
            name="test",
            description="desc",
            model_type=ModelType.TASK,
            tools=["Bash"],
            body="test.md",
        )
        assert spec.name == "test"
        assert spec.model_type == ModelType.TASK

    def test_color_default_none(self) -> None:
        spec = AgentSpec(
            name="x", description="d", model_type=ModelType.TASK, tools=[], body="x.md"
        )
        assert spec.color is None


class TestCommandSpec:
    def test_create(self) -> None:
        spec = CommandSpec(name="cmd", description="desc", body="cmd.md")
        assert spec.name == "cmd"


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_create(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        assert config.reasoning_model == "opus"
        assert config.task_model == "sonnet"


# ---------------------------------------------------------------------------
# ModelType
# ---------------------------------------------------------------------------


class TestModelType:
    def test_values(self) -> None:
        assert ModelType.REASONING == "reasoning"
        assert ModelType.TASK == "task"


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapter:
    def test_install_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.install_root() == tmp_path / ".claude"

    def test_agents_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.agents_dir() == tmp_path / ".claude" / "agents"

    def test_commands_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.commands_dir() == tmp_path / ".claude" / "commands"

    def test_reasoning_model(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.reasoning_model == "opus"

    def test_task_model(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.task_model == "sonnet"

    def test_get_default_config(self) -> None:
        config = ClaudeCodeAdapter.get_default_config()
        assert config.reasoning_model == "opus"
        assert config.task_model == "sonnet"

    def test_detect_installed_not(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("best_practices_rag.tui.shutil.which", lambda x: None)
        assert ClaudeCodeAdapter.detect_installed() is False

    def test_write_all_creates_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        # Create template files that will be loaded
        agents_dir = tmp_path / "resources" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "bp-pipeline.md").write_text("# bp-pipeline\n\nBody content")
        commands_dir = tmp_path / "resources" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "bp.md").write_text("# BP\n\nCommand content")
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="bp-pipeline.md",
                color="green",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
        written = adapter.write_all(agents, commands)
        assert (tmp_path / ".claude" / "agents" / "bp-pipeline.md").exists()
        assert (tmp_path / ".claude" / "commands" / "bp.md").exists()
        assert len(written) == 2

    def test_installed_file_relpaths(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="bp-pipeline.md",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
        relpaths = adapter.installed_file_relpaths(agents, commands)
        assert "agents/bp-pipeline.md" in relpaths
        assert "commands/bp.md" in relpaths


# ---------------------------------------------------------------------------
# OpenCodeAdapter
# ---------------------------------------------------------------------------


class TestOpenCodeAdapter:
    def test_install_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        assert adapter.install_root() == tmp_path / ".config" / "opencode"

    def test_reasoning_model(self) -> None:
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        assert adapter.reasoning_model == "glm-5"

    def test_task_model(self) -> None:
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        assert adapter.task_model == "minimax-m2.7"

    def test_write_all_creates_prompts_and_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        # Create template files
        agents_dir = tmp_path / "resources" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "bp-pipeline.md").write_text("Agent body")
        commands_dir = tmp_path / "resources" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "bp.md").write_text("Command body")
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="bp-pipeline.md",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
        written = adapter.write_all(agents, commands)
        prompts_dir = tmp_path / ".config" / "opencode" / "prompts"
        assert (prompts_dir / "bp-pipeline.md").exists()
        assert (prompts_dir / "bp.md").exists()
        json_path = tmp_path / ".config" / "opencode" / "opencode.json"
        assert json_path.exists()
        assert len(written) == 3

    def test_write_all_json_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        # Create template files
        agents_dir = tmp_path / "resources" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "bp-pipeline.md").write_text("Agent body")
        commands_dir = tmp_path / "resources" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "bp.md").write_text("Command body")
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="bp-pipeline.md",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
        adapter.write_all(agents, commands)
        config_json = json.loads(
            (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
        )
        assert config_json["$schema"] == "https://opencode.ai/config.json"
        agent = config_json["agent"]["bp-pipeline"]
        assert agent["mode"] == "subagent"
        assert agent["hidden"] is True
        assert agent["model"] == "minimax-m2.7"
        assert agent["prompt"] == "{file:prompts/bp-pipeline.md}"
        assert agent["tools"]["bash"] is True
        cmd = config_json["command"]["bp"]
        assert cmd["description"] == "Search"
        assert cmd["template"] == "{file:prompts/bp.md}"

    def test_write_all_merges_existing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        opencode_dir = tmp_path / ".config" / "opencode"
        opencode_dir.mkdir(parents=True)
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "agent": {"user-agent": {"mode": "primary", "model": "opencode-go/glm-5"}},
            "command": {"user-cmd": {"template": "user template"}},
        }
        (opencode_dir / "opencode.json").write_text(json.dumps(existing))
        # Create template files
        agents_dir = tmp_path / "resources" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "bp-pipeline.md").write_text("Agent body")
        commands_dir = tmp_path / "resources" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "bp.md").write_text("Command body")
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=[],
                body="bp-pipeline.md",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
        adapter.write_all(agents, commands)
        result = json.loads((opencode_dir / "opencode.json").read_text())
        assert "bp-pipeline" in result["agent"]
        assert "user-agent" in result["agent"]
        assert "bp" in result["command"]
        assert "user-cmd" in result["command"]

    def test_remove_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        opencode_dir = tmp_path / ".config" / "opencode"
        opencode_dir.mkdir(parents=True)
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "agent": {
                "bp-pipeline": {"mode": "subagent", "model": "minimax-m2.7"},
                "user-agent": {"mode": "primary", "model": "opencode-go/glm-5"},
            },
            "command": {
                "bp": {"template": "x"},
                "user-cmd": {"template": "y"},
            },
        }
        (opencode_dir / "opencode.json").write_text(json.dumps(existing))
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=[],
                body="bp-pipeline.md",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="bp.md")]
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
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=[],
                body="bp-pipeline.md",
            )
        ]
        adapter.remove_entries(agents, [])


# ---------------------------------------------------------------------------
# Registry and Factory
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_get_adapter_claude(self) -> None:
        adapter = get_adapter(TuiKind.CLAUDE)
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_get_adapter_opencode(self) -> None:
        adapter = get_adapter(TuiKind.OPENCODE)
        assert isinstance(adapter, OpenCodeAdapter)

    def test_register_adapter_is_callable(self) -> None:
        assert callable(register_adapter)


# ---------------------------------------------------------------------------
# detect_tuis
# ---------------------------------------------------------------------------


class TestDetectTuis:
    def test_detect_tuis_returns_list(self) -> None:
        result = detect_tuis()
        assert isinstance(result, list)
        assert all(isinstance(t, TuiKind) for t in result)


# ---------------------------------------------------------------------------
# resolve_tui_targets
# ---------------------------------------------------------------------------


class TestResolveTuiTargets:
    def test_both(self) -> None:
        result = resolve_tui_targets("both")
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE in result

    def test_claude(self) -> None:
        result = resolve_tui_targets("claude")
        assert result == [TuiKind.CLAUDE]

    def test_opencode(self) -> None:
        result = resolve_tui_targets("opencode")
        assert result == [TuiKind.OPENCODE]

    def test_auto(self) -> None:
        result = resolve_tui_targets("auto")
        assert isinstance(result, list)

    def test_unknown_defaults_to_claude(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("best_practices_rag.tui.detect_tuis", lambda: [])
        result = resolve_tui_targets("auto")
        assert result == [TuiKind.CLAUDE]
