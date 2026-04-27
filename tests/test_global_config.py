import json
from pathlib import Path

from best_practices_rag import global_config


def _patch_global_paths(monkeypatch, tmp_path: Path) -> Path:
    config_dir = tmp_path / ".config" / "best-practices-rag"
    monkeypatch.setattr(global_config, "GLOBAL_CONFIG_DIR", config_dir)
    monkeypatch.setattr(global_config, "GLOBAL_MODELS_PATH", config_dir / "models.json")
    return config_dir / "models.json"


def test_save_global_models_preserves_provider_sections(
    tmp_path: Path, monkeypatch
) -> None:
    models_path = _patch_global_paths(monkeypatch, tmp_path)

    global_config.save_global_models(
        {"reasoning": "open-reason", "task": "open-task"},
        provider="opencode",
    )
    global_config.save_global_models(
        {"reasoning": "codex-reason", "task": "codex-task"},
        provider="codex",
    )

    data = json.loads(models_path.read_text())
    assert data["opencode"] == {"reasoning": "open-reason", "task": "open-task"}
    assert data["codex"] == {"reasoning": "codex-reason", "task": "codex-task"}


def test_load_global_models_reads_requested_provider(
    tmp_path: Path, monkeypatch
) -> None:
    models_path = _patch_global_paths(monkeypatch, tmp_path)
    models_path.parent.mkdir(parents=True)
    models_path.write_text(
        json.dumps(
            {
                "opencode": {"reasoning": "open-reason", "task": "open-task"},
                "codex": {"reasoning": "codex-reason", "task": "codex-task"},
            }
        )
    )

    assert global_config.load_global_models("opencode") == {
        "reasoning": "open-reason",
        "task": "open-task",
    }
    assert global_config.load_global_models("codex") == {
        "reasoning": "codex-reason",
        "task": "codex-task",
    }
