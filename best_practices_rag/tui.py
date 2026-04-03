"""TUI adapter pattern for rendering agents and commands to Claude Code and OpenCode."""

import json
import shutil
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

    def remove_entries(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> None:
        """Remove agent and command entries from config. Override for TUI-specific behavior."""
        pass


class ClaudeCodeAdapter(TuiAdapter):
    _AGENT_TEMPLATE = """---
name: {name}
description: {description}
model: {model}
tools: {tools}
color: {color}
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
        return spec.body

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

        return files_written

    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]:
        result: list[str] = []
        for agent_spec in agents:
            result.append(f"agents/{agent_spec.name}.md")
        for command_spec in commands:
            result.append(f"commands/{command_spec.name}.md")
        return result


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
        models = load_global_models()
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
        return ModelConfig(reasoning_model="o4-mini", task_model="o4-mini")

    @classmethod
    def detect_installed(cls) -> bool:
        return shutil.which("codex") is not None

    def install_root(self) -> Path:
        return Path.home() / ".codex"

    def agents_dir(self) -> Path:
        return self.install_root() / "skills"

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
        lines = [f"Invoke the '{agent_name}' skill to {description}."]
        lines.append("Input:")
        for key, value in params:
            lines.append(f"  - {key}: {value}")
        lines.append("Wait for completion before continuing.")
        return "\n".join(lines)

    def render_agent(self, spec: AgentSpec) -> str:
        return f"---\nname: {spec.name}\ndescription: {self._yaml_escape(spec.description)}\n---\n\n{spec.body}"

    def render_command(self, spec: CommandSpec) -> str:
        return f"---\nname: {spec.name}\ndescription: {self._yaml_escape(spec.description)}\n---\n\n{spec.body}"

    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]:
        skills_root = self.install_root() / "skills"
        files_written: list[Path] = []

        for spec in agents:
            skill_dir = skills_root / spec.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            agents_dir = skill_dir / "agents"
            agents_dir.mkdir(parents=True, exist_ok=True)

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(self.render_agent(spec), encoding="utf-8")
            files_written.append(skill_md)
            print(f"  copied: {skill_md}")

            openai_yaml = agents_dir / "openai.yaml"
            openai_yaml.write_text(self._render_openai_yaml(spec), encoding="utf-8")
            files_written.append(openai_yaml)
            print(f"  copied: {openai_yaml}")

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
            result.append(f"skills/{spec.name}/SKILL.md")
            result.append(f"skills/{spec.name}/agents/openai.yaml")
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

    def _render_openai_yaml(self, spec: AgentSpec) -> str:
        name_escaped = self._yaml_escape(spec.name)
        desc_escaped = self._yaml_escape(spec.description)
        return (
            f"name: {name_escaped}\n"
            f"description: {desc_escaped}\n"
            "interface:\n"
            "  type: natural-language\n"
            "policy:\n"
            "  allow_implicit_invocation: false\n"
        )

    @staticmethod
    def _yaml_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


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
