"""TUI adapter pattern for rendering agents and commands to Claude Code and OpenCode."""

import json
import shutil
import subprocess
import tomllib
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import BaseModel, ConfigDict

from best_practices_rag.global_config import load_global_models


class TuiKind(StrEnum):
    CLAUDE = "claude"
    OPENCODE = "opencode"
    CODEX = "codex"


class ModelType(StrEnum):
    REASONING = "reasoning"
    TASK = "task"


class BpMode(StrEnum):
    CODEGEN = "codegen"
    RESEARCH = "research"

    @property
    def display_title(self) -> str:
        return "BP" if self == BpMode.CODEGEN else "BPR"

    @property
    def command_name(self) -> str:
        return "bp" if self == BpMode.CODEGEN else "bpr"

    @property
    def description(self) -> str:
        if self == BpMode.CODEGEN:
            return "Query the best-practices knowledge base for technology-specific guidance"
        return "Force gap-fill and resynthesis"


class ModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    reasoning_model: str
    task_model: str


class AgentSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    model_type: ModelType
    tools: list[str]
    body: str
    color: str | None = None


class CommandSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    body: str
    tools: list[str] = []


_BUILTIN_TOOL_MAP: dict[str, str] = {
    "Read": "read",
    "Write": "write",
    "Edit": "edit",
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
    "LS": "ls",
    "WebSearch": "webSearch",
    "WebFetch": "webFetch",
    "TodoWrite": "todoWrite",
    "NotebookEdit": "notebookEdit",
}


class TuiAdapter(ABC):
    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    @property
    def reasoning_model(self) -> str:
        return self._config.reasoning_model

    @property
    def task_model(self) -> str:
        return self._config.task_model

    @classmethod
    @abstractmethod
    def get_default_config(cls) -> ModelConfig: ...

    @classmethod
    @abstractmethod
    def detect_installed(cls) -> bool: ...

    @abstractmethod
    def install_root(self) -> Path: ...

    @abstractmethod
    def agents_dir(self) -> Path: ...

    @abstractmethod
    def commands_dir(self) -> Path: ...

    @abstractmethod
    def render_agent(self, spec: AgentSpec) -> str: ...

    @abstractmethod
    def render_command(self, spec: CommandSpec) -> str: ...

    @abstractmethod
    def render_command_invocation(self, command_name: str, args: str) -> str: ...

    @abstractmethod
    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]: ...

    @abstractmethod
    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]: ...

    @abstractmethod
    def reference_path(self, filename: str) -> str: ...

    @abstractmethod
    def render_agent_invocation(
        self,
        agent_name: str,
        description: str,
        params: list[tuple[str, str]],
    ) -> str: ...

    def permission_rules(self) -> list[str]:
        return []

    def remove_entries(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
        *,
        rules: list[str] | None = None,
    ) -> None:
        """Remove agent and command entries from config. Override for TUI-specific behavior.

        `rules` carries the permission rules recorded in the install manifest, for
        adapters that write them. The manifest helpers live in tui_install, which
        imports this module, so they are passed in rather than read here.
        """
        pass


# Permission rules the Claude Code install needs so /bp and /bpr run unprompted.
#
# Only Edit(...) and Read(...) path rules are consulted by Claude Code's file
# permission checks — Write(...), MultiEdit(...), NotebookEdit(...) and Glob(...)
# rules are inert and trigger a startup warning. See test_no_inert_permission_rules.
#
# Path anchoring in *user-level* settings.json: a bare relative pattern resolves
# against the session's working directory (the open project), while a leading "/"
# would resolve against ~/.claude/. Absolute paths therefore need a double slash.
_CLAUDE_PERMISSION_RULES: list[str] = [
    # Every best-practices-rag subcommand the command/agent templates shell out to.
    "Bash(best-practices-rag:*)",
    # Synthesis output documents, relative to whichever project is open.
    "Edit(.best-practices/**)",
    "Read(.best-practices/**)",
    # Intermediate files the pipeline writes via --output-file and reads back.
    "Read(//tmp/bp_exa_primary.md)",
    "Read(//tmp/bp_exa_failures.md)",
    "Read(//tmp/bp_exa_authority.md)",
    "Read(//tmp/bp_kb_bodies.txt)",
    # Documentation lookups performed by the bp-pipeline agent.
    "mcp__context7",
]

_CONTEXT7_MCP_NAME = "context7"
_CONTEXT7_MCP_PACKAGE = "@upstash/context7-mcp"


class ClaudeCodeAdapter(TuiAdapter):
    _AGENT_TEMPLATE = """---
name: {name}
description: {description}
model: {model}
tools: {tools}
color: {color}
---

{body}"""

    _COMMAND_TEMPLATE = """---
description: {description}{allowed_tools}
---

{body}"""

    @classmethod
    def get_default_config(cls) -> ModelConfig:
        return ModelConfig(reasoning_model="opus", task_model="sonnet")

    @classmethod
    def detect_installed(cls) -> bool:
        return shutil.which("claude") is not None

    def install_root(self) -> Path:
        return Path.home() / ".claude"

    def agents_dir(self) -> Path:
        return self.install_root() / "agents"

    def commands_dir(self) -> Path:
        return self.install_root() / "commands"

    def reference_path(self, filename: str) -> str:
        return f"~/.config/best-practices-rag/references/{filename}"

    def render_agent_invocation(
        self,
        agent_name: str,
        description: str,
        params: list[tuple[str, str]],
    ) -> str:
        lines = [f"Task({agent_name}):"]
        for key, value in params:
            lines.append(f"{key}: {value}")
        return "```text\n" + "\n".join(lines) + "\n```"

    def render_agent(self, spec: AgentSpec) -> str:
        model = (
            self.task_model
            if spec.model_type == ModelType.TASK
            else self.reasoning_model
        )
        color = spec.color or ""
        return self._AGENT_TEMPLATE.format(
            name=spec.name,
            description=spec.description,
            model=model,
            tools=", ".join(spec.tools),
            color=color,
            body=spec.body,
        )

    def render_command(self, spec: CommandSpec) -> str:
        # allowed-tools grants the listed tools for the turn the command is invoked;
        # it supplements the settings.json rules rather than replacing them.
        allowed_tools = (
            f"\nallowed-tools: {', '.join(spec.tools)}" if spec.tools else ""
        )
        return self._COMMAND_TEMPLATE.format(
            description=spec.description,
            allowed_tools=allowed_tools,
            body=spec.body,
        )

    def render_command_invocation(self, command_name: str, args: str) -> str:
        return f"/{command_name} {args}".rstrip()

    def settings_path(self) -> Path:
        return self.install_root() / "settings.json"

    def _merge_settings_json(self) -> Path | None:
        """Add the permission rules to ~/.claude/settings.json, preserving everything else.

        Returns the settings path on success, None if the file could not be read.
        Unlike the OpenCode merge, an unparseable file is left untouched rather than
        replaced — this file is the user's global Claude Code configuration.
        """
        settings_path = self.settings_path()
        settings: dict[str, Any] = {}

        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  [skip] could not read {settings_path}: {exc}")
                print("    Add these rules to permissions.allow by hand:")
                for rule in _CLAUDE_PERMISSION_RULES:
                    print(f"      {rule}")
                return None

        permissions: dict[str, Any] = settings.setdefault("permissions", {})
        allow: list[str] = permissions.setdefault("allow", [])

        added = [rule for rule in _CLAUDE_PERMISSION_RULES if rule not in allow]
        allow.extend(added)

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        if added:
            print(f"  updated: {settings_path} (+{len(added)} permission rules)")
        else:
            print(f"  up to date: {settings_path}")
        return settings_path

    def _register_context7_mcp(self) -> None:
        """Register the context7 MCP server via the claude CLI.

        ~/.claude.json is live state owned by Claude Code, so it is never edited
        directly. A failure here is a warning, not a failed install — the pipeline
        degrades to Exa search and training knowledge without context7.
        """
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            print("  [skip] claude not on PATH — context7 MCP server not registered")
            return

        listed = subprocess.run(
            [claude_bin, "mcp", "list"],
            capture_output=True,
            text=True,
        )
        # `claude mcp list` prints one "<name>: <command or url> - <status>" line per
        # server. Anchor on the name at line start — a bare substring test also matches
        # the package name in another server's command line.
        already_registered = listed.returncode == 0 and any(
            line.strip().startswith(f"{_CONTEXT7_MCP_NAME}:")
            for line in listed.stdout.splitlines()
        )
        if already_registered:
            print(f"  up to date: MCP server '{_CONTEXT7_MCP_NAME}'")
            return

        added = subprocess.run(
            [
                claude_bin,
                "mcp",
                "add",
                "-s",
                "user",
                _CONTEXT7_MCP_NAME,
                "--",
                "npx",
                "-y",
                _CONTEXT7_MCP_PACKAGE,
            ],
            capture_output=True,
            text=True,
        )
        if added.returncode == 0:
            print(f"  registered: MCP server '{_CONTEXT7_MCP_NAME}'")
        else:
            print(
                f"  [skip] could not register MCP server '{_CONTEXT7_MCP_NAME}': "
                f"{added.stderr.strip()}"
            )

    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]:
        agents_dir = self.agents_dir()
        commands_dir = self.commands_dir()
        agents_dir.mkdir(parents=True, exist_ok=True)
        commands_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[Path] = []

        for agent_spec in agents:
            file_path = agents_dir / f"{agent_spec.name}.md"
            file_path.write_text(self.render_agent(agent_spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        for command_spec in commands:
            file_path = commands_dir / f"{command_spec.name}.md"
            file_path.write_text(self.render_command(command_spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        settings_path = self._merge_settings_json()
        if settings_path is not None:
            files_written.append(settings_path)
        self._register_context7_mcp()

        return files_written

    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]:
        # settings.json is deliberately absent: it is shared with the user, so
        # _remove_stale_claude_files must never delete it. Same precedent as the
        # Codex adapter omitting config.toml.
        result: list[str] = []
        for agent_spec in agents:
            result.append(f"agents/{agent_spec.name}.md")
        for command_spec in commands:
            result.append(f"commands/{command_spec.name}.md")
        return result

    def permission_rules(self) -> list[str]:
        return list(_CLAUDE_PERMISSION_RULES)

    def remove_entries(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
        *,
        rules: list[str] | None = None,
    ) -> None:
        """Strip our permission rules from settings.json, leaving the user's intact.

        `rules` comes from the install manifest so an uninstall removes exactly what
        that install wrote, even if the rule set has changed since.
        """
        settings_path = self.settings_path()
        if not settings_path.exists():
            return
        try:
            settings: dict[str, Any] = json.loads(
                settings_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return

        to_remove = set(rules if rules is not None else _CLAUDE_PERMISSION_RULES)
        permissions: dict[str, Any] = settings.get("permissions", {})
        allow: list[str] = permissions.get("allow", [])
        remaining = [rule for rule in allow if rule not in to_remove]
        if remaining == allow:
            return

        if remaining:
            permissions["allow"] = remaining
        else:
            permissions.pop("allow", None)
            if not permissions:
                settings.pop("permissions", None)

        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"  updated: {settings_path} ({len(allow) - len(remaining)} rules removed)"
        )


class OpenCodeAdapter(TuiAdapter):
    def reference_path(self, filename: str) -> str:
        return f"~/.config/best-practices-rag/references/{filename}"

    def render_agent_invocation(
        self,
        agent_name: str,
        description: str,
        params: list[tuple[str, str]],
    ) -> str:
        lines = [f"Task({agent_name}):"]
        for key, value in params:
            lines.append(f"{key}: {value}")
        return "```text\n" + "\n".join(lines) + "\n```"

    @classmethod
    def get_default_config(cls) -> ModelConfig:
        models = load_global_models("opencode")
        return ModelConfig(
            reasoning_model=models.get("reasoning", "anthropic/claude-opus-4-6"),
            task_model=models.get("task", "anthropic/claude-sonnet-4-6"),
        )

    @classmethod
    def detect_installed(cls) -> bool:
        return (
            shutil.which("opencode") is not None
            or (Path.home() / ".opencode" / "bin" / "opencode").exists()
        )

    def install_root(self) -> Path:
        return Path.home() / ".config" / "opencode"

    def agents_dir(self) -> Path:
        return self.install_root() / "prompts"

    def commands_dir(self) -> Path:
        return self.install_root() / "prompts"

    def render_agent(self, spec: AgentSpec) -> str:
        return spec.body

    def render_command(self, spec: CommandSpec) -> str:
        return spec.body

    def render_command_invocation(self, command_name: str, args: str) -> str:
        return f"/{command_name} {args}".rstrip()

    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]:
        prompts_dir = self.agents_dir()
        prompts_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[Path] = []

        for agent_spec in agents:
            file_path = prompts_dir / f"{agent_spec.name}.md"
            file_path.write_text(self.render_agent(agent_spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        for command_spec in commands:
            file_path = prompts_dir / f"{command_spec.name}.md"
            file_path.write_text(self.render_command(command_spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        opencode_json_path = self.install_root() / "opencode.json"
        config = self._merge_config(opencode_json_path, agents, commands)
        opencode_json_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        files_written.append(opencode_json_path)
        print(f"  updated: {opencode_json_path}")

        return files_written

    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]:
        result: list[str] = []
        for agent_spec in agents:
            result.append(f"prompts/{agent_spec.name}.md")
        for command_spec in commands:
            result.append(f"prompts/{command_spec.name}.md")
        result.append("opencode.json")
        return result

    def remove_entries(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
        *,
        rules: list[str] | None = None,
    ) -> None:
        opencode_json_path = self.install_root() / "opencode.json"
        if not opencode_json_path.exists():
            return
        try:
            config: dict[str, Any] = json.loads(
                opencode_json_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return
        agent_block: dict[str, Any] = config.get("agent", {})
        command_block: dict[str, Any] = config.get("command", {})
        for agent_spec in agents:
            agent_block.pop(agent_spec.name, None)
        for command_spec in commands:
            command_block.pop(command_spec.name, None)
        opencode_json_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def _merge_config(
        self,
        config_path: Path,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> dict[str, Any]:
        if config_path.exists():
            try:
                existing: dict[str, Any] = json.loads(
                    config_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                existing = {}
        else:
            existing = {}

        existing.setdefault("$schema", "https://opencode.ai/config.json")
        agent_block: dict[str, Any] = existing.setdefault("agent", {})
        command_block: dict[str, Any] = existing.setdefault("command", {})

        for agent_spec in agents:
            model = (
                self.task_model
                if agent_spec.model_type == ModelType.TASK
                else self.reasoning_model
            )
            entry: dict[str, Any] = {
                "description": agent_spec.description,
                "mode": "subagent",
                "hidden": True,
                "model": model,
                "prompt": f"{{file:prompts/{agent_spec.name}.md}}",
            }
            tools_block = self._build_tools_block(agent_spec.tools)
            if tools_block:
                entry["tools"] = tools_block
            agent_block[agent_spec.name] = entry

        for command_spec in commands:
            command_block[command_spec.name] = {
                "description": command_spec.description,
                "template": f"{{file:prompts/{command_spec.name}.md}}",
            }

        return existing

    def _build_tools_block(self, tools: list[str]) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for tool in tools:
            if tool.startswith("mcp__") or tool.startswith("Task("):
                continue
            base = tool.split("(")[0]
            oc_key = _BUILTIN_TOOL_MAP.get(base)
            if oc_key:
                result[oc_key] = True
        return result


class CodexAdapter(TuiAdapter):
    @classmethod
    def get_default_config(cls) -> ModelConfig:
        models = load_global_models("codex")
        return ModelConfig(
            reasoning_model=models.get("reasoning", "o4-mini"),
            task_model=models.get("task", "o4-mini"),
        )

    @classmethod
    def detect_installed(cls) -> bool:
        return shutil.which("codex") is not None

    def install_root(self) -> Path:
        return Path.home() / ".codex"

    def agents_dir(self) -> Path:
        return self.install_root() / "agents"

    def commands_dir(self) -> Path:
        return self.install_root() / "skills"

    def reference_path(self, filename: str) -> str:
        return f"~/.config/best-practices-rag/references/{filename}"

    def render_agent_invocation(
        self,
        agent_name: str,
        description: str,
        params: list[tuple[str, str]],
    ) -> str:
        lines = [f"Spawn or delegate to the '{agent_name}' agent to {description}."]
        lines.append("Input:")
        for key, value in params:
            lines.append(f"  - {key}: {value}")
        lines.append("Wait for completion before continuing.")
        return "\n".join(lines)

    def render_agent(self, spec: AgentSpec) -> str:
        model = (
            self.task_model
            if spec.model_type == ModelType.TASK
            else self.reasoning_model
        )
        return (
            f"name = {self._yaml_escape(spec.name)}\n"
            f"description = {self._yaml_escape(spec.description)}\n"
            f"model = {self._yaml_escape(model)}\n"
            'sandbox_mode = "workspace-write"\n'
            'developer_instructions = """\n'
            f"{self._toml_multiline_escape(spec.body)}\n"
            '"""\n'
        )

    def render_command(self, spec: CommandSpec) -> str:
        return f"---\nname: {spec.name}\ndescription: {self._yaml_escape(spec.description)}\n---\n\n{spec.body}"

    def render_command_invocation(self, command_name: str, args: str) -> str:
        return f"${command_name} {args}".rstrip()

    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]:
        agents_dir = self.agents_dir()
        skills_root = self.install_root() / "skills"
        files_written: list[Path] = []

        for spec in agents:
            agents_dir.mkdir(parents=True, exist_ok=True)

            agent_toml = agents_dir / f"{spec.name}.toml"
            agent_toml.write_text(self.render_agent(spec), encoding="utf-8")
            files_written.append(agent_toml)
            print(f"  copied: {agent_toml}")

        for spec in commands:
            skill_dir = skills_root / spec.name
            skill_dir.mkdir(parents=True, exist_ok=True)

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(self.render_command(spec), encoding="utf-8")
            files_written.append(skill_md)
            print(f"  copied: {skill_md}")

        self._merge_config_toml()

        return files_written

    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]:
        result: list[str] = []
        for spec in agents:
            result.append(f"agents/{spec.name}.toml")
        for spec in commands:
            result.append(f"skills/{spec.name}/SKILL.md")
        return result

    def _merge_config_toml(self) -> None:
        config_path = self.install_root() / "config.toml"
        data: dict[str, Any] = {}

        if config_path.exists():
            try:
                data: dict[str, Any] = tomllib.loads(
                    config_path.read_text(encoding="utf-8")
                )
            except (tomllib.TOMLDecodeError, OSError):
                data = {}

        features: dict[str, Any] = data.setdefault("features", {})
        features["multi_agent"] = True

        mcp_servers: dict[str, Any] = data.setdefault("mcp_servers", {})
        if "context7" not in mcp_servers:
            mcp_servers["context7"] = {
                "command": "npx",
                "args": ["-y", "@anthropic-ai/context7-mcp-server"],
            }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(tomli_w.dumps(data), encoding="utf-8")

    @staticmethod
    def _yaml_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _toml_multiline_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


_ADAPTER_REGISTRY: dict[TuiKind, type[TuiAdapter]] = {
    TuiKind.CLAUDE: ClaudeCodeAdapter,
    TuiKind.OPENCODE: OpenCodeAdapter,
    TuiKind.CODEX: CodexAdapter,
}


def register_adapter(kind: TuiKind, adapter_class: type[TuiAdapter]) -> None:
    _ADAPTER_REGISTRY[kind] = adapter_class


def get_adapter(kind: TuiKind) -> TuiAdapter:
    adapter_class = _ADAPTER_REGISTRY[kind]
    config = adapter_class.get_default_config()
    return adapter_class(config)


def detect_tuis() -> list[TuiKind]:
    return [kind for kind, cls in _ADAPTER_REGISTRY.items() if cls.detect_installed()]


def resolve_tui_targets(tui: str) -> list[TuiKind]:
    """Resolve a --tui flag value to a list of TuiKind targets.

    auto     — detect installed TUIs, fallback to claude if none found
    claude   — Claude Code only
    opencode — OpenCode only
    codex    — OpenAI Codex only
    all      — all TUIs regardless of detection
    """
    if tui == "all":
        return [TuiKind.CLAUDE, TuiKind.OPENCODE, TuiKind.CODEX]
    if tui == "claude":
        return [TuiKind.CLAUDE]
    if tui == "opencode":
        return [TuiKind.OPENCODE]
    if tui == "codex":
        return [TuiKind.CODEX]
    detected = detect_tuis()
    return detected if detected else [TuiKind.CLAUDE]
