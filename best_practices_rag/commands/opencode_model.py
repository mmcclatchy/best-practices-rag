import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer
from exa_py import Exa
from rich.table import Table

from best_practices_rag.global_config import (
    load_api_key,
    save_api_key,
    save_global_models,
    GLOBAL_MODELS_PATH,
)
from best_practices_rag.ui.console import (
    console,
    print_error,
    print_info,
    print_warning,
)


_AA_MODELS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
_OPENCODE_GO_DOCS_URL = "https://opencode.ai/docs/go/"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_CACHE_DIR = Path.home() / ".config" / "best-practices-rag" / "cache"
_CACHE_TTL_SECONDS = 12 * 60 * 60


def _read_cache(name: str) -> dict | None:
    path = _CACHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        return data.get("payload")
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


_REASONING_INDEX = "artificial_analysis_intelligence_index"


def run(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept recommended mapping without prompting"
    ),
    aa_key: str | None = typer.Option(
        None,
        "--aa-key",
        help="Artificial Analysis API key (overrides ARTIFICIAL_ANALYSIS_API_KEY env var)",
    ),
    exa_key: str | None = typer.Option(
        None,
        "--exa-key",
        help="Exa API key for rate limit lookup (overrides EXA_API_KEY env var)",
    ),
    debug: bool = typer.Option(False, "--debug", help="Print debug info for API calls"),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Bypass cached API responses"
    ),
) -> int:
    aa_key_val = (
        aa_key
        or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "")
        or load_api_key("artificial_analysis")
        or ""
    )
    exa_key_val = (
        exa_key or os.environ.get("EXA_API_KEY", "") or load_api_key("exa") or ""
    )
    if aa_key and aa_key_val:
        save_api_key("artificial_analysis", aa_key_val)
    if exa_key and exa_key_val:
        save_api_key("exa", exa_key_val)
    if no_cache:
        _clear_cache()

    provider, models = _discover_models()
    if not models:
        print_error(
            "No OpenCode models found. Ensure opencode is installed and configured."
        )
        return 1

    console.print(f"Provider: [cyan]{provider}[/cyan]")
    console.print(f"Available models: {', '.join(models)}\n")

    if aa_key_val:
        print_info("Fetching benchmark data from Artificial Analysis...")
        aa_data = _fetch_aa_data(aa_key_val, debug=debug)
    else:
        print_warning("ARTIFICIAL_ANALYSIS_API_KEY not set — skipping benchmark lookup")
        print_warning(
            "Set ARTIFICIAL_ANALYSIS_API_KEY or use --aa-key for benchmark-backed recommendations"
        )
        aa_data = {}

    rate_limits: dict[str, str] = {}
    if exa_key_val:
        rate_limits = _fetch_rate_limits(exa_key_val, provider, debug=debug)

    scored_by_tier = _score_models_by_tier(
        models, aa_data, rate_limits=rate_limits, debug=debug
    )

    if aa_data or rate_limits:
        intelligence_by_model = dict(scored_by_tier["reasoning"])
        task_with_intelligence = [
            (model_id, intelligence_by_model.get(model_id, 0.0))
            for model_id, _ in scored_by_tier["task"]
        ]
        _display_tier_table(
            "Reasoning Scores", scored_by_tier["reasoning"], "Intelligence", rate_limits
        )
        _display_tier_table(
            "Task Scores", task_with_intelligence, "Intelligence", rate_limits
        )

    suggestion = _suggest_tiers(scored_by_tier)

    if yes:
        mapping = suggestion
    else:
        mapping = _interactive_override(suggestion, scored_by_tier)
        if mapping is None:
            print_warning("Mapping not saved")
            return 1

    save_global_models(mapping)
    console.print(
        f"\n[bold green]✓[/bold green] Saved to [cyan]{_config_path()}[/cyan]"
    )
    print_info(
        "Run 'best-practices-rag setup --tui opencode' to apply new models to your config"
    )
    return 0


def _discover_models() -> tuple[str, list[str]]:
    provider = _detect_provider()
    if not provider:
        return "", []
    models = _list_models(provider)
    return provider, models


def _detect_provider() -> str:
    try:
        result = subprocess.run(
            ["opencode", "providers", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        clean = _ANSI_ESCAPE.sub("", result.stdout)
        for line in clean.splitlines():
            if "●" not in line:
                continue
            name_part = line.split("●", 1)[1].strip()
            name_part = re.split(r"\s+api\b", name_part, flags=re.IGNORECASE)[0].strip()
            if name_part:
                return name_part.lower().replace(" ", "-")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _list_models(provider: str) -> list[str]:
    try:
        result = subprocess.run(
            ["opencode", "models", provider],
            capture_output=True,
            text=True,
            timeout=10,
        )
        models = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped and "/" in stripped:
                models.append(stripped)
        return models
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _fetch_aa_data(aa_key: str, *, debug: bool = False) -> dict[str, dict[str, float]]:
    cached = _read_cache("aa_data")
    if cached is not None:
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
        all_fields = {_REASONING_INDEX}
        models_list = (
            data if isinstance(data, list) else data.get("models", data.get("data", []))
        )
        if debug:
            console.print(
                f"[dim]  AA response type: {type(data).__name__}, models: {len(models_list)}[/dim]"
            )
        with_evals = 0
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
                with_evals += 1
        if debug:
            console.print(
                f"[dim]  AA models with scores: {with_evals}/{len(models_list)}[/dim]"
            )
        _write_cache("aa_data", result)
        return result
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as exc:
        if debug:
            console.print(f"[red]  AA error: {type(exc).__name__}: {exc}[/red]")
        print_warning(
            "Could not fetch Artificial Analysis data — falling back to interactive selection"
        )
        return {}


def _fetch_rate_limits(
    exa_key: str, provider: str, *, debug: bool = False
) -> dict[str, str]:
    cached = _read_cache("rate_limits")
    if cached is not None:
        if debug:
            console.print(
                f"[dim]  Exa using cached rate limits ({len(cached)} models)[/dim]"
            )
        return cached
    if debug:
        console.print(f"[dim]  Exa get_contents({_OPENCODE_GO_DOCS_URL})[/dim]")
    try:
        exa = Exa(api_key=exa_key)
        response = exa.get_contents(urls=[_OPENCODE_GO_DOCS_URL], text=True)
        if not response.results:
            if debug:
                console.print("[dim]  Exa returned no results[/dim]")
            return {}
        text = response.results[0].text or ""
        if debug:
            console.print(f"[dim]  Exa text length: {len(text)} chars[/dim]")
            console.print(f"[dim]  Exa text preview: {text[:300]!r}[/dim]")
        parsed = _parse_rate_limits_table(text, provider)
        if debug:
            console.print(f"[dim]  Parsed rate limits: {parsed}[/dim]")
        if parsed:
            _write_cache("rate_limits", parsed)
        return parsed
    except Exception as exc:
        if debug:
            console.print(f"[red]  Exa error: {type(exc).__name__}: {exc}[/red]")
        print_warning("Could not fetch rate limits — skipping")
        return {}


def _parse_rate_limits_table(text: str, provider: str) -> dict[str, str]:
    lines = text.splitlines()
    header_line = ""
    data_line = ""
    for i, line in enumerate(lines):
        if "requests per 5 hour" in line.lower():
            data_line = line
            for j in range(i - 1, -1, -1):
                candidate = lines[j].strip()
                if candidate.startswith("|") and "---" not in candidate:
                    header_line = candidate
                    break
            break

    if not header_line or not data_line:
        return {}

    headers = [h.strip() for h in header_line.split("|") if h.strip()]
    values = [v.strip() for v in data_line.split("|") if v.strip()]

    if values and values[0].lower().startswith("requests"):
        values = values[1:]

    result: dict[str, str] = {}
    for name, val in zip(headers, values):
        model_id = f"{provider}/{name.lower().replace(' ', '-')}"
        result[model_id] = val
    return result


def _parse_rate_limit_value(val: str) -> int:
    return int(val.replace(",", "").strip())


def _score_models_by_tier(
    models: list[str],
    aa_data: dict[str, dict[str, float]],
    rate_limits: dict[str, str] | None = None,
    *,
    debug: bool = False,
) -> dict[str, list[tuple[str, float]]]:
    reasoning_scored: list[tuple[str, float]] = []
    task_scored: list[tuple[str, float]] = []

    parsed_rates: dict[str, int] = {}
    if rate_limits:
        parsed_rates = {m: _parse_rate_limit_value(v) for m, v in rate_limits.items()}

    for model_id in models:
        short = model_id.split("/", 1)[-1].lower()
        match = _find_aa_match(short, aa_data)
        if debug:
            status = f'matched "{match}"' if match else "no match"
            console.print(f"[dim]  {model_id} -> {status}[/dim]")

        intelligence = aa_data[match].get(_REASONING_INDEX, 0.0) if match else 0.0
        reasoning_scored.append((model_id, intelligence))

        throughput = float(parsed_rates.get(model_id, 0))
        task_scored.append((model_id, throughput))

    return {
        "reasoning": sorted(reasoning_scored, key=lambda x: x[1], reverse=True),
        "task": sorted(task_scored, key=lambda x: x[1], reverse=True),
    }


def _normalize_name(name: str) -> str:
    return name.lower().replace("-", " ").replace("_", " ").strip()


def _find_aa_match(short_name: str, aa_data: dict[str, dict[str, float]]) -> str:
    normalized = _normalize_name(short_name)
    candidates: list[tuple[int, str]] = []
    for key in aa_data:
        norm_key = _normalize_name(key)
        if norm_key == normalized:
            return key
        if norm_key.startswith(normalized + " ("):
            candidates.append((len(norm_key), key))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    return ""


def _suggest_tiers(
    scored_by_tier: dict[str, list[tuple[str, float]]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    reasoning = scored_by_tier.get("reasoning", [])
    task = scored_by_tier.get("task", [])
    if reasoning:
        mapping["reasoning"] = reasoning[0][0]
    has_throughput = any(score > 0 for _, score in task)
    if has_throughput:
        mapping["task"] = task[0][0]
    elif len(reasoning) >= 2:
        mapping["task"] = reasoning[1][0]
    elif reasoning:
        mapping["task"] = reasoning[0][0]
    return mapping


def _display_tier_table(
    title: str,
    scored: list[tuple[str, float]],
    score_label: str,
    rate_limits: dict[str, str],
    extra_scores: dict[str, float] | None = None,
    extra_label: str = "",
    format_int: bool = False,
) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Model")
    table.add_column(score_label, justify="right")
    if extra_scores:
        table.add_column(extra_label, justify="right")
    if rate_limits:
        table.add_column("Reqs/5hr", justify="right")
    for model_id, score in scored:
        short = model_id.split("/", 1)[-1]
        if format_int:
            score_text = f"{int(score):,}" if score else "[dim]no data[/dim]"
        else:
            score_text = f"{score:.1f}" if score else "[dim]no data[/dim]"
        row: list[str] = [short, score_text]
        if extra_scores:
            extra = extra_scores.get(model_id, 0.0)
            row.append(f"{extra:.1f}" if extra else "[dim]no data[/dim]")
        if rate_limits:
            row.append(rate_limits.get(model_id, "\u2014"))
        table.add_row(*row)
    console.print()
    console.print(table)


def _interactive_override(
    suggestion: dict[str, str],
    scored_by_tier: dict[str, list[tuple[str, float]]],
) -> dict[str, str] | None:
    mapping: dict[str, str] = {}

    for tier in ("reasoning", "task"):
        options = scored_by_tier.get(tier, [])

        console.print(f"\n[bold]{tier.title()} model:[/bold]")
        for i, (model_id, score) in enumerate(options, 1):
            score_text = f"({score:.1f})" if score else ""
            console.print(f"  [bold][{i}][/bold] {model_id}  {score_text}")

        while True:
            raw = console.input(f"  Select [1-{len(options)}]: ").strip()
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(options):
                    mapping[tier] = options[index - 1][0]
                    break
            console.print(f"  [red]Enter a number 1-{len(options)}.[/red]")

    response = console.input("\nAccept this mapping? [Y/n] ").strip().lower()
    if response in ("n", "no"):
        return None
    return mapping


def _config_path() -> str:
    return str(GLOBAL_MODELS_PATH)
