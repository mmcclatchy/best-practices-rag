import json
from pathlib import Path
from typing import Any


GLOBAL_CONFIG_DIR = Path.home() / ".config" / "best-practices-rag"
GLOBAL_MODELS_PATH = GLOBAL_CONFIG_DIR / "models.json"
GLOBAL_API_KEYS_PATH = GLOBAL_CONFIG_DIR / "api_keys.json"


def load_global_models() -> dict[str, str]:
    if not GLOBAL_MODELS_PATH.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(
            GLOBAL_MODELS_PATH.read_text(encoding="utf-8")
        )
        return data.get("opencode", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_global_models(models: dict[str, str]) -> None:
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if GLOBAL_MODELS_PATH.exists():
        try:
            existing = json.loads(GLOBAL_MODELS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    existing["opencode"] = models
    GLOBAL_MODELS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_api_key(service: str) -> str | None:
    if not GLOBAL_API_KEYS_PATH.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(
            GLOBAL_API_KEYS_PATH.read_text(encoding="utf-8")
        )
        return data.get(service)
    except (json.JSONDecodeError, OSError):
        return None


def save_api_key(service: str, key: str) -> None:
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if GLOBAL_API_KEYS_PATH.exists():
        try:
            existing = json.loads(GLOBAL_API_KEYS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    existing[service] = key
    GLOBAL_API_KEYS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
