"""TUI adapter pattern for rendering agents and commands to Claude Code and OpenCode."""

import json
import shutil
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any

from best_practices_rag.global_config import load_global_models
from pydantic import BaseModel, ConfigDict


class TuiKind(StrEnum):
    CLAUDE = "claude"
    OPENCODE = "opencode"


class ModelType(StrEnum):
    REASONING = "reasoning"
    TASK = "task"


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

    def _load_agent_body(self, filename: str) -> str:
        template_dir = Path(__file__).parent / "resources" / "agents"
        return (template_dir / filename).read_text(encoding="utf-8")

    def _load_command_body(self, filename: str) -> str:
        template_dir = Path(__file__).parent / "resources" / "commands"
        return (template_dir / filename).read_text(encoding="utf-8")

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

    def render_agent(self, spec: AgentSpec) -> str:
        body = self._load_agent_body(spec.body)
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
            body=body,
        )

    def render_command(self, spec: CommandSpec) -> str:
        return self._load_command_body(spec.body)

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

        for spec in agents:
            file_path = agents_dir / f"{spec.name}.md"
            file_path.write_text(self.render_agent(spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        for spec in commands:
            file_path = commands_dir / f"{spec.name}.md"
            file_path.write_text(self.render_command(spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        return files_written

    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]:
        result: list[str] = []
        for spec in agents:
            result.append(f"agents/{spec.name}.md")
        for spec in commands:
            result.append(f"commands/{spec.name}.md")
        return result


class OpenCodeAdapter(TuiAdapter):
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
        return self._load_agent_body(spec.body)

    def render_command(self, spec: CommandSpec) -> str:
        return self._load_command_body(spec.body)

    def write_all(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[Path]:
        prompts_dir = self.agents_dir()
        prompts_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[Path] = []

        for spec in agents:
            file_path = prompts_dir / f"{spec.name}.md"
            file_path.write_text(self.render_agent(spec), encoding="utf-8")
            files_written.append(file_path)
            print(f"  copied: {file_path}")

        for spec in commands:
            file_path = prompts_dir / f"{spec.name}.md"
            file_path.write_text(self.render_command(spec), encoding="utf-8")
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
        for spec in agents:
            result.append(f"prompts/{spec.name}.md")
        for spec in commands:
            result.append(f"prompts/{spec.name}.md")
        result.append("opencode.json")
        return result

    def remove_entries(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> None:
        """Remove our agent and command entries from opencode.json without deleting the file."""
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
        for spec in agents:
            agent_block.pop(spec.name, None)
        for spec in commands:
            command_block.pop(spec.name, None)
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

        for spec in agents:
            model = (
                self.task_model
                if spec.model_type == ModelType.TASK
                else self.reasoning_model
            )
            entry: dict[str, Any] = {
                "description": spec.description,
                "mode": "subagent",
                "hidden": True,
                "model": model,
                "prompt": f"{{file:prompts/{spec.name}.md}}",
            }
            tools_block = self._build_tools_block(spec.tools)
            if tools_block:
                entry["tools"] = tools_block
            agent_block[spec.name] = entry

        for spec in commands:
            command_block[spec.name] = {
                "description": spec.description,
                "template": f"{{file:prompts/{spec.name}.md}}",
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


_ADAPTER_REGISTRY: dict[TuiKind, type[TuiAdapter]] = {
    TuiKind.CLAUDE: ClaudeCodeAdapter,
    TuiKind.OPENCODE: OpenCodeAdapter,
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

    auto   — detect installed TUIs, fallback to claude if none found
    claude — Claude Code only
    opencode — OpenCode only
    both   — both regardless of detection
    """
    if tui == "both":
        return [TuiKind.CLAUDE, TuiKind.OPENCODE]
    if tui == "claude":
        return [TuiKind.CLAUDE]
    if tui == "opencode":
        return [TuiKind.OPENCODE]
    detected = detect_tuis()
    return detected if detected else [TuiKind.CLAUDE]
