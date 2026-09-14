import subprocess

import pytest

from best_practices_rag import global_config
from best_practices_rag import tui


@pytest.fixture(autouse=True)
def no_real_mcp_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ClaudeCodeAdapter.write_all from invoking the real `claude` binary.

    write_all registers the context7 MCP server by shelling out to `claude mcp add`.
    Without this, running the suite on a machine that has Claude Code installed would
    mutate the developer's own user-scoped MCP configuration.
    """

    def _fake_run(
        cmd: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if len(cmd) > 1 and cmd[1] == "mcp":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess call in tests: {cmd}")

    monkeypatch.setattr(tui.subprocess, "run", _fake_run)


@pytest.fixture(autouse=True)
def isolated_global_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Keep the developer's own ~/.config/best-practices-rag out of the suite.

    global_config resolves its paths at import time, so patching Path.home in a
    test does not redirect them: model lookups fall through to the real
    models.json and assertions on default models pass or fail per machine.
    """
    config_dir = tmp_path_factory.mktemp("global-config")
    monkeypatch.setattr(global_config, "GLOBAL_CONFIG_DIR", config_dir)
    monkeypatch.setattr(global_config, "GLOBAL_MODELS_PATH", config_dir / "models.json")
    monkeypatch.setattr(
        global_config, "GLOBAL_API_KEYS_PATH", config_dir / "api_keys.json"
    )
