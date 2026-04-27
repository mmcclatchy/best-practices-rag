from pathlib import Path

from best_practices_rag._release import RELEASE_MANIFEST


def test_release_manifest_includes_imported_top_level_modules() -> None:
    package_dir = Path("best_practices_rag")
    top_level_modules = {
        str(path)
        for path in package_dir.glob("*.py")
        if path.name not in {"_release.py"}
    }

    missing = sorted(top_level_modules - set(RELEASE_MANIFEST))

    assert missing == []
