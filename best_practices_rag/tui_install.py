"""Shared install helpers for TUI adapters."""

import json
import shutil
from pathlib import Path

from best_practices_rag import __version__
from best_practices_rag.agent_defs import build_specs
from best_practices_rag.tui import (
    AgentSpec,
    CommandSpec,
    TuiAdapter,
    TuiKind,
    get_adapter,
    resolve_tui_targets,
)


def _copy_tree(src: Path, dst: Path, *, force: bool) -> list[str]:
    copied: list[str] = []
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.exists() and not force:
            print(f"  skip (exists): {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(str(rel))
        print(f"  copied: {target}")
    return copied


def _read_manifest(config_dir: Path) -> dict[str, list[str]]:
    path = config_dir / "manifest.json"
    if not path.exists():
        return {"files": [], "opencode_files": [], "codex_files": []}
    try:
        data = json.loads(path.read_text())
        return {
            "files": data.get("files", []),
            "opencode_files": data.get("opencode_files", []),
            "codex_files": data.get("codex_files", []),
        }
    except Exception:
        return {"files": [], "opencode_files": [], "codex_files": []}


def _write_manifest(
    config_dir: Path,
    claude_files: set[str],
    opencode_files: set[str] | None = None,
    codex_files: set[str] | None = None,
) -> None:
    (config_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": __version__,
                "files": sorted(claude_files),
                "opencode_files": sorted(opencode_files or set()),
                "codex_files": sorted(codex_files or set()),
            },
            indent=2,
        )
    )


def _remove_stale_claude_files(
    claude_dir: Path, config_dir: Path, new_files: set[str]
) -> None:
    manifest = _read_manifest(config_dir)
    stale: set[str] = {f for f in manifest["files"] if f not in new_files}

    # Namespace scan: catch bp-*.md agents installed before manifest tracking existed
    agents_dir = claude_dir / "agents"
    if agents_dir.exists():
        for f in agents_dir.glob("bp-*.md"):
            rel = f"agents/{f.name}"
            if rel not in new_files:
                stale.add(rel)

    for rel in stale:
        target = claude_dir / rel
        if target.exists():
            target.unlink()
            print(f"  removed (stale): {target}")


def _remove_stale_opencode_files(
    opencode_root: Path, config_dir: Path, new_files: set[str]
) -> None:
    manifest = _read_manifest(config_dir)
    # opencode.json is merged, not removed as stale
    stale: set[str] = {
        f
        for f in manifest["opencode_files"]
        if f not in new_files and f != "opencode.json"
    }
    for rel in stale:
        target = opencode_root / rel
        if target.exists():
            target.unlink()
            print(f"  removed (stale): {target}")


def _remove_stale_codex_files(
    codex_root: Path, config_dir: Path, new_files: set[str]
) -> None:
    manifest = _read_manifest(config_dir)
    # config.toml is merged, not removed as stale
    stale: set[str] = {
        f for f in manifest["codex_files"] if f not in new_files and f != "config.toml"
    }
    for rel in stale:
        target = codex_root / rel
        if target.exists():
            target.unlink()
            print(f"  removed (stale): {target}")

    # Namespace scan: bp-pipeline used to be installed as a Codex skill.
    # It is now a Codex agent, so remove stale internal-skill installs even
    # when no manifest is available from the old installation.
    stale_pipeline_skill = codex_root / "skills" / "bp-pipeline"
    if stale_pipeline_skill.exists() and "skills/bp-pipeline/SKILL.md" not in new_files:
        shutil.rmtree(stale_pipeline_skill)
        print(f"  removed (stale): {stale_pipeline_skill}")


def _install_tui_files(
    adapter: TuiAdapter,
    agents: list[AgentSpec],
    commands: list[CommandSpec],
) -> tuple[list[Path], list[str]]:
    written = adapter.write_all(agents, commands)
    relpaths = adapter.installed_file_relpaths(agents, commands)
    return written, relpaths


def _compute_tui_relpaths(adapter: TuiAdapter) -> list[str]:
    agents, commands = build_specs(adapter)
    return adapter.installed_file_relpaths(agents, commands)


def _refresh_installed_tui_files(
    *,
    tui: str,
    config_dir: Path,
    claude_dir: Path,
    bundle: Path,
) -> None:
    tui_targets = resolve_tui_targets(tui)

    _copy_tree(
        bundle / "skills" / "best-practices-rag" / "references",
        config_dir / "references",
        force=True,
    )

    manifest = _read_manifest(config_dir)

    if TuiKind.CLAUDE in tui_targets:
        expected_claude = set(_compute_tui_relpaths(get_adapter(TuiKind.CLAUDE)))
        _remove_stale_claude_files(claude_dir, config_dir, expected_claude)

    claude_tui_files: set[str] = set(manifest["files"])
    opencode_tui_files: set[str] = set(manifest["opencode_files"])
    codex_tui_files: set[str] = set(manifest["codex_files"])

    for tui_kind in tui_targets:
        adapter = get_adapter(tui_kind)
        if tui_kind == TuiKind.OPENCODE:
            _remove_stale_opencode_files(adapter.install_root(), config_dir, set())
        elif tui_kind == TuiKind.CODEX:
            _remove_stale_codex_files(adapter.install_root(), config_dir, set())
        agents, commands = build_specs(adapter)
        _, relpaths = _install_tui_files(adapter, agents, commands)
        if tui_kind == TuiKind.CLAUDE:
            claude_tui_files = set(relpaths)
        elif tui_kind == TuiKind.OPENCODE:
            opencode_tui_files = set(relpaths)
        elif tui_kind == TuiKind.CODEX:
            codex_tui_files = set(relpaths)

    _write_manifest(config_dir, claude_tui_files, opencode_tui_files, codex_tui_files)
