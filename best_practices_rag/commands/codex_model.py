import json
import os
import select
import subprocess
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import typer
from rich.table import Table

from best_practices_rag.global_config import (
    GLOBAL_MODELS_PATH,
    load_api_key,
    save_api_key,
    save_global_models,
)
from best_practices_rag.tui_install import _refresh_installed_tui_files
from best_practices_rag.ui.console import (
    console,
    print_error,
    print_info,
    print_warning,
)


_AA_MODELS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
_CACHE_DIR = Path.home() / ".config" / "best-practices-rag" / "cache"
_CACHE_TTL_SECONDS = 12 * 60 * 60
_REASONING_INDEX = "artificial_analysis_intelligence_index"
_CODING_INDEX = "artificial_analysis_coding_index"
_CODEX_APP_SERVER_CMD = ["codex", "app-server", "--listen", "stdio://"]
_CODEX_UPDATE_CMD = ["npm", "install", "-g", "@openai/codex"]
_CODEX_DISCOVERY_CACHE_KEY = "codex_models_discovered"
_CODEX_DISCOVERY_TIMEOUT_SECONDS = 15
_CODEX_DISCOVERY_PAGE_LIMIT = 100


def run(
    aa_key: str | None = typer.Option(
        None,
        "--aa-key",
        help="Artificial Analysis API key (overrides ARTIFICIAL_ANALYSIS_API_KEY env var)",
    ),
    debug: bool = typer.Option(False, "--debug", help="Print debug info for API calls"),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Bypass cached API responses"
    ),
    include_hidden: bool = typer.Option(
        False,
        "--include-hidden",
        help="Include hidden models that do not appear in the default Codex picker",
    ),
    update_codex: bool = typer.Option(
        False,
        "--update-codex",
        help="Update Codex CLI with npm before discovering models",
    ),
    no_update_codex: bool = typer.Option(
        False,
        "--no-update-codex",
        help="Skip the Codex CLI update prompt before discovering models",
    ),
    reasoning_model: str | None = typer.Option(
        None, "--reasoning-model", help="Set reasoning model directly"
    ),
    task_model: str | None = typer.Option(
        None, "--task-model", help="Set task model directly"
    ),
    no_apply: bool = typer.Option(
        False,
        "--no-apply",
        help="Save global model mapping only; skip regenerating Codex artifacts",
    ),
) -> int:
    if update_codex and no_update_codex:
        print_error("Use only one of --update-codex or --no-update-codex")
        return 1

    if reasoning_model or task_model:
        mapping = _build_direct_mapping(reasoning_model, task_model)
        return _save_and_apply(mapping, no_apply=no_apply)

    aa_key_val = (
        aa_key
        or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
        or load_api_key("artificial_analysis")
        or ""
    )
    if aa_key and aa_key_val:
        save_api_key("artificial_analysis", aa_key_val)
    if no_cache:
        _clear_cache()

    if not _maybe_update_codex_cli(
        update_codex=update_codex, no_update_codex=no_update_codex
    ):
        return 1

    discovered = _discover_codex_models(include_hidden=include_hidden, debug=debug)
    if not discovered:
        return 1

    models = [entry["id"] for entry in discovered]
    console.print("Provider: [cyan]codex[/cyan]")
    console.print(f"Available models: {', '.join(models)}\n")

    if aa_key_val:
        print_info("Fetching benchmark data from Artificial Analysis...")
        aa_data = _fetch_aa_data(aa_key_val, debug=debug)
        if aa_data:
            _display_aa_table(discovered, aa_data)
    else:
        print_info("ARTIFICIAL_ANALYSIS_API_KEY not set — skipping benchmark context.")

    mapping = _interactive_select_models(discovered)
    if mapping is None:
        print_warning("Mapping not saved")
        return 1

    return _save_and_apply(mapping, no_apply=no_apply)


def _build_direct_mapping(
    reasoning_model: str | None,
    task_model: str | None,
) -> dict[str, str]:
    reasoning = str(reasoning_model or task_model or "").strip()
    task = str(task_model or reasoning_model or "").strip()
    return {"reasoning": reasoning, "task": task}


def _save_and_apply(mapping: dict[str, str], *, no_apply: bool) -> int:
    save_global_models(mapping, provider="codex")
    console.print(
        f"\n[bold green]✓[/bold green] Saved to [cyan]{_config_path()}[/cyan]"
    )
    return _auto_apply_to_codex(no_apply=no_apply)


def _auto_apply_to_codex(*, no_apply: bool) -> int:
    if no_apply:
        print_info(
            "Auto-apply skipped (--no-apply). Run 'best-practices-rag setup --tui codex' when ready."
        )
        return 0

    config_dir = Path.home() / ".config" / "best-practices-rag"
    config_dir.mkdir(parents=True, exist_ok=True)
    try:
        _refresh_installed_tui_files(
            tui="codex",
            config_dir=config_dir,
            claude_dir=Path.home() / ".claude",
            bundle=_bundle_root(),
        )
    except Exception as exc:
        print_warning(f"Auto-apply failed: {exc}")
        print_info("Run 'best-practices-rag setup --tui codex' to apply saved models.")
        return 1

    print_info("Applied saved Codex model tiers to generated agents and skills.")
    return 0


def _bundle_root() -> Path:
    return Path(str(files("best_practices_rag") / "resources"))


def _maybe_update_codex_cli(*, update_codex: bool, no_update_codex: bool) -> bool:
    if no_update_codex:
        print_info("Codex CLI update skipped (--no-update-codex).")
        return True

    should_update = update_codex
    if not should_update:
        response = (
            console.input(
                "Update Codex CLI before discovering models? "
                "[dim]Runs: npm install -g @openai/codex[/dim] [y/N] "
            )
            .strip()
            .lower()
        )
        should_update = response in ("y", "yes")

    if not should_update:
        print_info("Codex CLI update skipped.")
        return True

    print_info("Updating Codex CLI with npm install -g @openai/codex...")
    try:
        result = subprocess.run(_CODEX_UPDATE_CMD)
    except (FileNotFoundError, OSError) as exc:
        print_error(f"Could not update Codex CLI: {exc}")
        return False

    if result.returncode != 0:
        print_error(f"Codex CLI update failed with exit code {result.returncode}")
        return False

    print_info("Codex CLI update completed.")
    return True


def _read_cache(name: str) -> dict | list | None:
    path = _CACHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        payload = data.get("payload")
        if isinstance(payload, (dict, list)):
            return payload
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(name: str, payload: object) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {"_cached_at": time.time(), "payload": payload}
        (_CACHE_DIR / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _clear_cache() -> None:
    if not _CACHE_DIR.exists():
        return
    for f in _CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)


def _discover_codex_models(
    *, include_hidden: bool, debug: bool = False
) -> list[dict[str, Any]]:
    discovered_all: list[dict[str, Any]] = []
    try:
        discovered_all = _fetch_codex_models_live(debug=debug)
        _write_cache(_CODEX_DISCOVERY_CACHE_KEY, discovered_all)
    except RuntimeError as exc:
        cached = _read_cache(_CODEX_DISCOVERY_CACHE_KEY)
        discovered_all = _normalize_discovered_models(cached)
        if discovered_all:
            print_warning(
                f"Live Codex model discovery failed ({exc}) — using cached model list"
            )
        else:
            print_error(f"Could not discover Codex models: {exc}")
            print_info(
                "Ensure Codex is installed and authenticated, then rerun 'best-practices-rag models codex'."
            )
            return []

    filtered = [
        entry for entry in discovered_all if include_hidden or not entry["hidden"]
    ]
    if not filtered:
        if include_hidden:
            print_error("Codex model discovery returned no models.")
            return []
        print_error(
            "No non-hidden Codex models discovered. Retry with --include-hidden."
        )
        return []

    return filtered


def _fetch_codex_models_live(*, debug: bool = False) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None

    while True:
        page = _request_codex_model_page(cursor=cursor, debug=debug)
        data = page.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Codex app-server returned malformed model/list payload")
        for item in data:
            if isinstance(item, dict):
                collected.append(item)

        next_cursor = page.get("nextCursor")
        if not next_cursor:
            break
        if not isinstance(next_cursor, str):
            raise RuntimeError("Codex app-server returned non-string nextCursor")
        if next_cursor in seen_cursors:
            raise RuntimeError("Codex app-server returned a repeated pagination cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    models = _normalize_discovered_models(collected)
    if not models:
        raise RuntimeError("Codex app-server returned an empty model list")

    if debug:
        console.print(f"[dim]  Codex discovered models: {len(models)}[/dim]")

    return models


def _request_codex_model_page(
    *, cursor: str | None, debug: bool = False
) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            _CODEX_APP_SERVER_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"failed to start Codex app-server: {exc}") from exc

    try:
        _write_json_line(
            process,
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "best-practices-rag",
                        "title": "best-practices-rag",
                        "version": "0.0.0",
                    },
                    "capabilities": None,
                },
            },
        )
        _write_json_line(process, {"method": "initialized"})

        params: dict[str, Any] = {
            "includeHidden": True,
            "limit": _CODEX_DISCOVERY_PAGE_LIMIT,
        }
        if cursor:
            params["cursor"] = cursor
        _write_json_line(process, {"method": "model/list", "id": 1, "params": params})

        result = _read_response_for_id(
            process,
            request_id=1,
            timeout_seconds=_CODEX_DISCOVERY_TIMEOUT_SECONDS,
        )
        if debug:
            count = (
                len(result.get("data", []))
                if isinstance(result.get("data"), list)
                else 0
            )
            console.print(
                f"[dim]  Codex model/list page received: {count} models[/dim]"
            )
        return result
    finally:
        _shutdown_process(process)


def _write_json_line(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if process.stdin is None:
        raise RuntimeError("Codex app-server stdin unavailable")
    try:
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()
    except OSError as exc:
        raise RuntimeError(f"failed writing to Codex app-server stdin: {exc}") from exc


def _read_response_for_id(
    process: subprocess.Popen[str],
    *,
    request_id: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        message = _read_next_json_message(process, deadline)
        if message is None:
            if process.poll() is not None:
                break
            continue

        if message.get("id") != request_id:
            continue

        if "error" in message:
            raise RuntimeError(f"Codex app-server returned error: {message['error']}")

        result = message.get("result")
        if isinstance(result, dict):
            return result
        raise RuntimeError("Codex app-server returned a non-object result payload")

    stderr_tail = _read_stderr_tail(process)
    if stderr_tail:
        raise RuntimeError(f"Codex app-server response timeout/failure: {stderr_tail}")
    raise RuntimeError("timed out waiting for Codex app-server response")


def _read_next_json_message(
    process: subprocess.Popen[str], deadline: float
) -> dict[str, Any] | None:
    if process.stdout is None:
        return None

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            ready, _, _ = select.select([process.stdout], [], [], remaining)
        except (OSError, ValueError):
            return None
        if not ready:
            return None

        line = process.stdout.readline()
        if line == "":
            return None

        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return None


def _read_stderr_tail(process: subprocess.Popen[str]) -> str:
    if process.stderr is None:
        return ""
    try:
        text = process.stderr.read() or ""
    except OSError:
        return ""
    return text.strip()[:300]


def _shutdown_process(process: subprocess.Popen[str]) -> None:
    if process.stdin is not None and not process.stdin.closed:
        try:
            process.stdin.close()
        except OSError:
            pass

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


def _normalize_discovered_models(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        raw_data = cast(dict[str, Any], raw)

        model_id = str(raw_data.get("id") or raw_data.get("model") or "").strip()
        if not model_id or model_id in seen_ids:
            continue

        display_name = (
            str(
                raw_data.get("displayName") or raw_data.get("display_name") or model_id
            ).strip()
            or model_id
        )
        description = str(raw_data.get("description") or "").strip()
        hidden = bool(raw_data.get("hidden", False))
        is_default = bool(raw_data.get("isDefault", raw_data.get("is_default", False)))

        normalized.append(
            {
                "id": model_id,
                "display_name": display_name,
                "description": description,
                "hidden": hidden,
                "is_default": is_default,
            }
        )
        seen_ids.add(model_id)

    return normalized


def _fetch_aa_data(aa_key: str, *, debug: bool = False) -> dict[str, dict[str, float]]:
    cached = _read_cache("aa_data_codex")
    if isinstance(cached, dict):
        if debug:
            console.print(f"[dim]  AA using cached data ({len(cached)} models)[/dim]")
        return cached

    req = urllib.request.Request(
        _AA_MODELS_URL,
        headers={"x-api-key": aa_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result: dict[str, dict[str, float]] = {}
        all_fields = {_REASONING_INDEX, _CODING_INDEX}
        models_list = (
            data if isinstance(data, list) else data.get("models", data.get("data", []))
        )
        for model in models_list:
            name = (model.get("name") or model.get("slug") or "").lower()
            if not name:
                continue
            evals = model.get("evaluations") or {}
            scores: dict[str, float] = {}
            for field in all_fields:
                val = evals.get(field)
                if val is not None:
                    scores[field] = float(val)
            if scores:
                result[name] = scores
        _write_cache("aa_data_codex", result)
        return result
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        print_warning(
            "Could not fetch Artificial Analysis data — skipping benchmark context"
        )
        return {}


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").replace("_", " ").split())


def _find_aa_match(
    model_id: str, aa_data: dict[str, dict[str, float]], aliases: set[str] | None = None
) -> str:
    model_norm = _normalize_name(model_id)
    candidate_aliases = {model_norm}
    if aliases:
        candidate_aliases.update(_normalize_name(alias) for alias in aliases)

    for key in aa_data:
        norm_key = _normalize_name(key)
        if norm_key in candidate_aliases:
            return key
    for key in aa_data:
        norm_key = _normalize_name(key)
        if any(alias in norm_key for alias in candidate_aliases):
            return key
    return ""


def _display_aa_table(
    models: list[dict[str, Any]], aa_data: dict[str, dict[str, float]]
) -> None:
    table = Table(
        title="Codex Model Benchmarks", show_header=True, header_style="bold cyan"
    )
    table.add_column("Model")
    table.add_column("Intelligence", justify="right")
    table.add_column("Coding", justify="right")
    table.add_column("Match", justify="right")

    for model in models:
        model_id = str(model["id"])
        aliases = {str(model.get("display_name") or "")}
        match = _find_aa_match(model_id, aa_data, aliases=aliases)
        intelligence = aa_data.get(match, {}).get(_REASONING_INDEX, 0.0)
        coding = aa_data.get(match, {}).get(_CODING_INDEX, 0.0)
        table.add_row(
            model_id,
            f"{intelligence:.1f}" if intelligence else "[dim]no data[/dim]",
            f"{coding:.1f}" if coding else "[dim]no data[/dim]",
            "AA" if match else "[dim]none[/dim]",
        )

    console.print()
    console.print(table)
    console.print(
        "[dim]Artificial Analysis metrics are informational only; choose each tier manually.[/dim]"
    )


def _interactive_select_models(models: list[dict[str, Any]]) -> dict[str, str] | None:
    mapping: dict[str, str] = {}
    options = [str(model["id"]) for model in models]

    for tier in ("reasoning", "task"):
        console.print(f"\n[bold]{tier.title()} model:[/bold]")
        for i, model_id in enumerate(options, 1):
            console.print(f"  [bold][{i}][/bold] {model_id}")

        while True:
            raw = console.input(f"  Select [1-{len(options)}]: ").strip()
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(options):
                    mapping[tier] = options[index - 1]
                    break
            console.print(f"  [red]Enter a number 1-{len(options)}.[/red]")

    response = console.input("\nAccept this mapping? [Y/n] ").strip().lower()
    if response in ("n", "no"):
        return None
    return mapping


def _config_path() -> str:
    return str(GLOBAL_MODELS_PATH)
