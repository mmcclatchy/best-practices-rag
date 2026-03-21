from pathlib import Path
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from best_practices_rag.setup_schema import run_migrations


def test_main_runs_migrations(mocker: MockerFixture) -> None:
    mock_executor_cls = mocker.patch("best_practices_rag.setup_schema.Executor")
    mock_executor = MagicMock()
    mock_executor_cls.return_value = mock_executor
    mock_executor.migrate.return_value = None

    mocker.patch(
        "best_practices_rag.setup_schema.get_settings", return_value=MagicMock()
    )
    mocker.patch("best_practices_rag.setup_schema.GraphDatabase.driver")

    run_migrations()

    mock_executor_cls.assert_called_once()
    call_kwargs = mock_executor_cls.call_args
    assert isinstance(
        call_kwargs.kwargs.get("migrations_path") or call_kwargs.args[1], Path
    )
    mock_executor.migrate.assert_called_once()


def test_migrations_directory_exists() -> None:
    migrations_path = Path("best_practices_rag/migrations")
    assert migrations_path.is_dir()
    cypher_files = list(migrations_path.glob("V*.cypher"))
    assert len(cypher_files) >= 1
    assert any("V0001" in f.name for f in cypher_files)
