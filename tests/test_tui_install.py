"""Coverage for the Claude Code settings.json permission install path."""

import json
from pathlib import Path
from typing import Any

import pytest

from best_practices_rag.tui import (
    AgentSpec,
    ClaudeCodeAdapter,
    CommandSpec,
    ModelConfig,
    ModelType,
)


# A settings file shaped like a real one: the statusLine command is a multi-line
# shell script with embedded newlines, ANSI escapes and nested quotes — exactly the
# value a careless JSON round-trip mangles.
_STATUS_LINE = (
    "input=$(cat)\nmodel=$(printf '%s' \"$input\" | jq -r '.model.display_name')\n"
    "RESET='\\033[0m'\nBOLD='\\033[1m'\n"
    'printf "${BOLD}%s${RESET}\\n" "$model"'
)


def _existing_settings() -> dict[str, Any]:
    return {
        "includeCoAuthoredBy": False,
        "permissions": {
            "allow": ["Bash(uv run:*)", "Bash(grep:*)"],
            "deny": ["Edit(.claude/agents/respec*)"],
            "additionalDirectories": ["/home/someone/.claude/best-practices"],
        },
        "model": "opus",
        "statusLine": {"type": "command", "command": _STATUS_LINE},
        "theme": "dark",
    }


def _adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ClaudeCodeAdapter:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return ClaudeCodeAdapter(ModelConfig(reasoning_model="opus", task_model="sonnet"))


def _sample_agents() -> list[AgentSpec]:
    return [
        AgentSpec(
            name="bp-pipeline",
            description="Pipeline",
            model_type=ModelType.TASK,
            tools=["Bash"],
            body="# bp-pipeline\n\nBody",
            color="green",
        )
    ]


def _sample_commands() -> list[CommandSpec]:
    return [
        CommandSpec(
            name="bp",
            description="Search",
            body="# BP\n\nBody",
            tools=["Bash(best-practices-rag:*)", "Read"],
        )
    ]


class TestMergeSettingsJson:
    def test_preserves_unrelated_keys_and_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        original = _existing_settings()
        settings_path.write_text(json.dumps(original, indent=2))

        adapter.write_all(_sample_agents(), _sample_commands())
        result = json.loads(settings_path.read_text())

        # Every non-permissions key survives untouched, statusLine script included.
        for key in ["includeCoAuthoredBy", "model", "statusLine", "theme"]:
            assert result[key] == original[key]
        assert result["statusLine"]["command"] == _STATUS_LINE

        # The user's own allow/deny/additionalDirectories entries are all still there.
        assert result["permissions"]["allow"][:2] == ["Bash(uv run:*)", "Bash(grep:*)"]
        assert result["permissions"]["deny"] == original["permissions"]["deny"]
        assert (
            result["permissions"]["additionalDirectories"]
            == original["permissions"]["additionalDirectories"]
        )

        for rule in adapter.permission_rules():
            assert rule in result["permissions"]["allow"]

    def test_is_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps(_existing_settings(), indent=2))

        adapter.write_all(_sample_agents(), _sample_commands())
        first = settings_path.read_bytes()
        adapter.write_all(_sample_agents(), _sample_commands())

        assert settings_path.read_bytes() == first

    def test_creates_file_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())

        result = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert result == {"permissions": {"allow": adapter.permission_rules()}}

    def test_leaves_unparseable_file_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text("{ not valid json")

        adapter.write_all(_sample_agents(), _sample_commands())

        assert settings_path.read_text() == "{ not valid json"


class TestRemoveEntries:
    def test_removes_only_our_rules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps(_existing_settings(), indent=2))

        adapter.write_all(_sample_agents(), _sample_commands())
        adapter.remove_entries(
            _sample_agents(), _sample_commands(), rules=adapter.permission_rules()
        )
        result = json.loads(settings_path.read_text())

        assert result["permissions"]["allow"] == ["Bash(uv run:*)", "Bash(grep:*)"]
        assert result["permissions"]["deny"] == ["Edit(.claude/agents/respec*)"]
        assert result["statusLine"]["command"] == _STATUS_LINE

    def test_uses_manifest_rules_not_current_constant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An older install's rules are removed even after the rule set changes."""
        adapter = _adapter(tmp_path, monkeypatch)
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(
            json.dumps(
                {"permissions": {"allow": ["Read(//tmp/bp_legacy.md)", "Bash(ls:*)"]}}
            )
        )

        adapter.remove_entries(
            _sample_agents(), _sample_commands(), rules=["Read(//tmp/bp_legacy.md)"]
        )
        result = json.loads(settings_path.read_text())

        assert result["permissions"]["allow"] == ["Bash(ls:*)"]

    def test_drops_empty_containers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        adapter.write_all(_sample_agents(), _sample_commands())
        adapter.remove_entries(
            _sample_agents(), _sample_commands(), rules=adapter.permission_rules()
        )

        result = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert result == {}

    def test_no_settings_file_is_a_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = _adapter(tmp_path, monkeypatch)
        adapter.remove_entries(_sample_agents(), _sample_commands(), rules=[])

        assert not (tmp_path / ".claude" / "settings.json").exists()


class TestPermissionRuleForm:
    def test_no_inert_permission_rules(self) -> None:
        """Write(), MultiEdit(), NotebookEdit() and Glob() path rules match nothing.

        Claude Code's file permission checks only consult Edit() and Read(); the other
        four forms are silently inert and warned about at startup. Guard the generator
        so a future edit cannot reintroduce one.
        """
        adapter = ClaudeCodeAdapter(
            ModelConfig(reasoning_model="opus", task_model="sonnet")
        )
        inert = ("Write(", "MultiEdit(", "NotebookEdit(", "Glob(")

        for rule in adapter.permission_rules():
            assert not rule.startswith(inert), f"{rule} is inert; use Edit(/Read("

    def test_absolute_paths_use_double_slash(self) -> None:
        adapter = ClaudeCodeAdapter(
            ModelConfig(reasoning_model="opus", task_model="sonnet")
        )
        for rule in adapter.permission_rules():
            if "/tmp/" in rule:
                assert "(//tmp/" in rule, f"{rule} would resolve under ~/.claude/"


class TestCommandFrontmatter:
    def test_claude_commands_carry_description_and_allowed_tools(self) -> None:
        adapter = ClaudeCodeAdapter(
            ModelConfig(reasoning_model="opus", task_model="sonnet")
        )
        rendered = adapter.render_command(_sample_commands()[0])

        assert rendered.startswith("---\n")
        assert "description: Search" in rendered
        assert "allowed-tools: Bash(best-practices-rag:*), Read" in rendered
        assert rendered.endswith("# BP\n\nBody")

    def test_allowed_tools_omitted_when_no_tools(self) -> None:
        adapter = ClaudeCodeAdapter(
            ModelConfig(reasoning_model="opus", task_model="sonnet")
        )
        rendered = adapter.render_command(
            CommandSpec(name="bp", description="Search", body="# BP")
        )

        assert "allowed-tools:" not in rendered
        assert "description: Search" in rendered
