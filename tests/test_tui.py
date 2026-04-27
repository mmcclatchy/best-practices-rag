"""Tests for best_practices_rag/tui.py — TUI adapter pattern."""

import json
import tomllib
from pathlib import Path

import pytest

from best_practices_rag import global_config
from best_practices_rag.tui import (
    AgentSpec,
    BpMode,
    ClaudeCodeAdapter,
    CodexAdapter,
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
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="# bp-pipeline\n\nBody content",
                color="green",
            )
        ]
        commands = [
            CommandSpec(name="bp", description="Search", body="# BP\n\nCommand content")
        ]
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
                body="# bp-pipeline\n\nBody content",
            )
        ]
        commands = [
            CommandSpec(name="bp", description="Search", body="# BP\n\nCommand content")
        ]
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
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="Agent body",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="Command body")]
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
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=["Bash"],
                body="Agent body",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="Command body")]
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
        agents = [
            AgentSpec(
                name="bp-pipeline",
                description="Pipeline",
                model_type=ModelType.TASK,
                tools=[],
                body="Agent body",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="Command body")]
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
                body="Agent body",
            )
        ]
        commands = [CommandSpec(name="bp", description="Search", body="Command body")]
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
                body="Agent body",
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

    def test_get_adapter_codex(self) -> None:
        adapter = get_adapter(TuiKind.CODEX)
        assert isinstance(adapter, CodexAdapter)

    def test_register_adapter_is_callable(self) -> None:
        assert callable(register_adapter)

    def test_opencode_adapter_reads_opencode_global_models(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / ".config" / "best-practices-rag"
        monkeypatch.setattr(global_config, "GLOBAL_CONFIG_DIR", config_dir)
        monkeypatch.setattr(
            global_config, "GLOBAL_MODELS_PATH", config_dir / "models.json"
        )
        global_config.save_global_models(
            {"reasoning": "open-reason", "task": "open-task"},
            provider="opencode",
        )
        global_config.save_global_models(
            {"reasoning": "codex-reason", "task": "codex-task"},
            provider="codex",
        )

        adapter = get_adapter(TuiKind.OPENCODE)

        assert adapter.reasoning_model == "open-reason"
        assert adapter.task_model == "open-task"

    def test_codex_adapter_reads_codex_global_models(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / ".config" / "best-practices-rag"
        monkeypatch.setattr(global_config, "GLOBAL_CONFIG_DIR", config_dir)
        monkeypatch.setattr(
            global_config, "GLOBAL_MODELS_PATH", config_dir / "models.json"
        )
        global_config.save_global_models(
            {"reasoning": "open-reason", "task": "open-task"},
            provider="opencode",
        )
        global_config.save_global_models(
            {"reasoning": "codex-reason", "task": "codex-task"},
            provider="codex",
        )

        adapter = get_adapter(TuiKind.CODEX)

        assert adapter.reasoning_model == "codex-reason"
        assert adapter.task_model == "codex-task"


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
    def test_all(self) -> None:
        result = resolve_tui_targets("all")
        assert TuiKind.CLAUDE in result
        assert TuiKind.OPENCODE in result
        assert TuiKind.CODEX in result

    def test_claude(self) -> None:
        result = resolve_tui_targets("claude")
        assert result == [TuiKind.CLAUDE]

    def test_opencode(self) -> None:
        result = resolve_tui_targets("opencode")
        assert result == [TuiKind.OPENCODE]

    def test_codex(self) -> None:
        result = resolve_tui_targets("codex")
        assert result == [TuiKind.CODEX]

    def test_auto(self) -> None:
        result = resolve_tui_targets("auto")
        assert isinstance(result, list)

    def test_unknown_defaults_to_claude(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("best_practices_rag.tui.detect_tuis", lambda: [])
        result = resolve_tui_targets("auto")
        assert result == [TuiKind.CLAUDE]


# ---------------------------------------------------------------------------
# BpMode
# ---------------------------------------------------------------------------


class TestBpMode:
    def test_codegen_value(self) -> None:
        assert BpMode.CODEGEN == "codegen"

    def test_research_value(self) -> None:
        assert BpMode.RESEARCH == "research"

    def test_codegen_display_title(self) -> None:
        assert BpMode.CODEGEN.display_title == "BP"

    def test_research_display_title(self) -> None:
        assert BpMode.RESEARCH.display_title == "BPR"

    def test_codegen_command_name(self) -> None:
        assert BpMode.CODEGEN.command_name == "bp"

    def test_research_command_name(self) -> None:
        assert BpMode.RESEARCH.command_name == "bpr"

    def test_codegen_description(self) -> None:
        assert (
            "best-practices" in BpMode.CODEGEN.description.lower()
            or "knowledge" in BpMode.CODEGEN.description.lower()
        )

    def test_research_description(self) -> None:
        assert BpMode.RESEARCH.description == "Force gap-fill and resynthesis"


# ---------------------------------------------------------------------------
# reference_path and render_agent_invocation
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterReferencePath:
    def test_reference_path_format(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        result = adapter.reference_path("tech-versions.md")
        assert result == "~/.config/best-practices-rag/references/tech-versions.md"

    def test_reference_path_synthesis_research(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        result = adapter.reference_path("synthesis-format-research.md")
        assert (
            result
            == "~/.config/best-practices-rag/references/synthesis-format-research.md"
        )

    def test_render_agent_invocation_format(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        result = adapter.render_agent_invocation(
            agent_name="bp-pipeline",
            description="run pipeline",
            params=[("MODE", "codegen"), ("TECH", "fastapi")],
        )
        assert "Task(bp-pipeline):" in result
        assert "MODE: codegen" in result
        assert "TECH: fastapi" in result
        assert result.startswith("```text\n")
        assert result.endswith("```")

    def test_render_agent_invocation_empty_params(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        result = adapter.render_agent_invocation(
            agent_name="test-agent",
            description="test",
            params=[],
        )
        assert "Task(test-agent):" in result

    def test_render_command_invocation_uses_slash_prefix(self) -> None:
        config = ModelConfig(reasoning_model="opus", task_model="sonnet")
        adapter = ClaudeCodeAdapter(config)
        assert adapter.render_command_invocation("bp", "<query>") == "/bp <query>"
        assert (
            adapter.render_command_invocation("bpr", "$ARGUMENTS") == "/bpr $ARGUMENTS"
        )


class TestOpenCodeAdapterReferencePath:
    def test_reference_path_format(self) -> None:
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        result = adapter.reference_path("tech-versions.md")
        assert result == "~/.config/best-practices-rag/references/tech-versions.md"

    def test_render_agent_invocation_format(self) -> None:
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        result = adapter.render_agent_invocation(
            agent_name="bp-pipeline",
            description="run pipeline",
            params=[("MODE", "research")],
        )
        assert "Task(bp-pipeline):" in result
        assert "MODE: research" in result

    def test_render_command_invocation_uses_slash_prefix(self) -> None:
        config = ModelConfig(reasoning_model="glm-5", task_model="minimax-m2.7")
        adapter = OpenCodeAdapter(config)
        assert adapter.render_command_invocation("bp", "<query>") == "/bp <query>"
        assert (
            adapter.render_command_invocation("bpr", "$ARGUMENTS") == "/bpr $ARGUMENTS"
        )


# ---------------------------------------------------------------------------
# CodexAdapter
# ---------------------------------------------------------------------------


def _make_codex_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CodexAdapter:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config = ModelConfig(reasoning_model="o4-mini", task_model="o4-mini")
    return CodexAdapter(config)


def _sample_agents() -> list[AgentSpec]:
    return [
        AgentSpec(
            name="bp-pipeline",
            description="Run the best-practices pipeline",
            model_type=ModelType.TASK,
            tools=["Bash"],
            body="# bp-pipeline body",
        )
    ]


def _sample_commands() -> list[CommandSpec]:
    return [
        CommandSpec(name="bp", description="Search best practices", body="# BP body"),
        CommandSpec(
            name="bpr", description="Research best practices", body="# BPR body"
        ),
    ]


class TestCodexAdapter:
    def test_install_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        assert adapter.install_root() == tmp_path / ".codex"

    def test_agents_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        assert adapter.agents_dir() == tmp_path / ".codex" / "agents"

    def test_commands_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        assert adapter.commands_dir() == tmp_path / ".codex" / "skills"

    def test_reference_path_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        result = adapter.reference_path("tech-versions.md")
        assert result == "~/.config/best-practices-rag/references/tech-versions.md"

    def test_render_command_invocation_uses_dollar_prefix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        assert adapter.render_command_invocation("bp", "<query>") == "$bp <query>"
        assert (
            adapter.render_command_invocation("bpr", "$ARGUMENTS") == "$bpr $ARGUMENTS"
        )

    def test_render_agent_invocation_contains_agent_delegation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        result = adapter.render_agent_invocation(
            agent_name="bp-pipeline",
            description="run the best-practices pipeline",
            params=[("MODE", "codegen")],
        )
        assert "Spawn or delegate to the 'bp-pipeline' agent" in result
        assert "Invoke the 'bp-pipeline' skill" not in result

    def test_render_agent_invocation_no_task_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        result = adapter.render_agent_invocation(
            agent_name="bp-pipeline",
            description="run the best-practices pipeline",
            params=[("MODE", "codegen")],
        )
        assert "Task(bp-pipeline):" not in result

    def test_render_agent_generates_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        spec = AgentSpec(
            name="bp-pipeline",
            description="Pipeline",
            model_type=ModelType.TASK,
            tools=[],
            body="body content\ncommand " + "\\" + "\nnext",
        )
        result = adapter.render_agent(spec)
        data = tomllib.loads(result)
        assert data["name"] == "bp-pipeline"
        assert data["description"] == "Pipeline"
        assert data["model"] == "o4-mini"
        assert data["sandbox_mode"] == "workspace-write"
        assert data["developer_instructions"] == "body content\ncommand \\\nnext\n"

    def test_render_agent_uses_configured_task_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        adapter = CodexAdapter(
            ModelConfig(reasoning_model="codex-reason", task_model="codex-task")
        )
        spec = AgentSpec(
            name="bp-pipeline",
            description="Pipeline",
            model_type=ModelType.TASK,
            tools=[],
            body="body content",
        )

        data = tomllib.loads(adapter.render_agent(spec))

        assert data["model"] == "codex-task"

    def test_render_command_generates_frontmatter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        spec = CommandSpec(name="bp", description="Search", body="body content")
        result = adapter.render_command(spec)
        assert "name:" in result
        assert "description:" in result

    def test_write_all_creates_agent_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())
        assert (tmp_path / ".codex" / "agents" / "bp-pipeline.toml").exists()
        assert (tmp_path / ".codex" / "skills" / "bp" / "SKILL.md").exists()
        assert (tmp_path / ".codex" / "skills" / "bpr" / "SKILL.md").exists()

    def test_write_all_does_not_create_agent_skill_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())
        assert not (
            tmp_path / ".codex" / "skills" / "bp-pipeline" / "SKILL.md"
        ).exists()
        assert not (
            tmp_path / ".codex" / "skills" / "bp-pipeline" / "agents" / "openai.yaml"
        ).exists()

    def test_write_all_creates_config_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())
        config_toml = tmp_path / ".codex" / "config.toml"
        assert config_toml.exists()
        assert "context7" in config_toml.read_text()

    def test_merge_config_toml_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())
        adapter.write_all(_sample_agents(), _sample_commands())
        text = (tmp_path / ".codex" / "config.toml").read_text()
        # The mcp_servers.context7 section header must appear exactly once
        assert text.count("[mcp_servers.context7]") == 1

    def test_installed_file_relpaths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _make_codex_adapter(tmp_path, monkeypatch)
        relpaths = adapter.installed_file_relpaths(_sample_agents(), _sample_commands())
        assert "agents/bp-pipeline.toml" in relpaths
        assert "skills/bp/SKILL.md" in relpaths
        assert "skills/bpr/SKILL.md" in relpaths
        assert "skills/bp-pipeline/SKILL.md" not in relpaths
        assert "skills/bp-pipeline/agents/openai.yaml" not in relpaths
