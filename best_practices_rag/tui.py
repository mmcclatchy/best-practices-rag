"""TUI adapter pattern for rendering agents and commands to Claude Code and OpenCode."""

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    model: str
    tools: list[str]
    body: str
    color: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    body: str


class TuiKind(str, Enum):
    CLAUDE = "claude"
    OPENCODE = "opencode"


_MODEL_MAP: dict[str, str] = {
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku": "anthropic/claude-haiku-4-5",
}

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
    def model_name(self, short_name: str) -> str: ...

    @abstractmethod
    def installed_file_relpaths(
        self,
        agents: list[AgentSpec],
        commands: list[CommandSpec],
    ) -> list[str]: ...


class ClaudeCodeAdapter(TuiAdapter):
    def install_root(self) -> Path:
        return Path.home() / ".claude"

    def agents_dir(self) -> Path:
        return self.install_root() / "agents"

    def commands_dir(self) -> Path:
        return self.install_root() / "commands"

    def model_name(self, short_name: str) -> str:
        return short_name

    def render_agent(self, spec: AgentSpec) -> str:
        parts = [
            "---",
            f"name: {spec.name}",
            f"description: {spec.description}",
            f"model: {self.model_name(spec.model)}",
        ]
        if spec.color:
            parts.append(f"color: {spec.color}")
        parts.append(f"tools: {', '.join(spec.tools)}")
        parts.append("---")
        return "\n".join(parts) + "\n\n" + spec.body

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
    def install_root(self) -> Path:
        return Path.home() / ".config" / "opencode"

    def agents_dir(self) -> Path:
        return self.install_root() / "prompts"

    def commands_dir(self) -> Path:
        return self.install_root() / "prompts"

    def model_name(self, short_name: str) -> str:
        return _MODEL_MAP.get(short_name, f"anthropic/claude-{short_name}")

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
            entry: dict[str, Any] = {
                "description": spec.description,
                "mode": "subagent",
                "hidden": True,
                "model": self.model_name(spec.model),
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


def get_adapter(kind: TuiKind) -> TuiAdapter:
    if kind == TuiKind.CLAUDE:
        return ClaudeCodeAdapter()
    return OpenCodeAdapter()


def detect_tuis() -> list[TuiKind]:
    result: list[TuiKind] = []
    if shutil.which("claude"):
        result.append(TuiKind.CLAUDE)
    if (
        shutil.which("opencode")
        or (Path.home() / ".opencode" / "bin" / "opencode").exists()
    ):
        result.append(TuiKind.OPENCODE)
    return result


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


def parse_claude_agent(text: str) -> AgentSpec:
    if not text.startswith("---"):
        raise ValueError("Agent file missing YAML frontmatter")
    end = text.find("---", 3)
    if end == -1:
        raise ValueError("Agent file has unclosed frontmatter")

    block = text[3:end].strip()
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()

    body = text[end + 3 :].lstrip("\n")
    tools_raw = fm.get("tools", "")
    tools = [t.strip() for t in tools_raw.split(",") if t.strip()] if tools_raw else []

    return AgentSpec(
        name=fm.get("name", ""),
        description=fm.get("description", ""),
        model=fm.get("model", "sonnet"),
        tools=tools,
        body=body,
        color=fm.get("color") or None,
    )


def parse_claude_command(text: str, name: str) -> CommandSpec:
    """Parse a Claude Code command file into a CommandSpec.

    Extracts description from the first H1 heading; strips YAML frontmatter if present.
    """
    description = name  # fallback

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            description = stripped[2:].strip()
            break

    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            body = text[end + 3 :].lstrip("\n")

    return CommandSpec(name=name, description=description, body=body)
