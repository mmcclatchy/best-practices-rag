from pathlib import Path

from best_practices_rag._release import RELEASE_MANIFEST, _default_target


def test_release_manifest_includes_imported_top_level_modules() -> None:
    package_dir = Path("best_practices_rag")
    top_level_modules = {
        str(path)
        for path in package_dir.glob("*.py")
        if path.name not in {"_release.py"}
    }

    missing = sorted(top_level_modules - set(RELEASE_MANIFEST))

    assert missing == []


def test_default_target_is_the_sibling_without_the_dev_suffix() -> None:
    dev_root = Path("/home/someone/code/best-practices-rag-dev")

    assert _default_target(dev_root) == Path("/home/someone/code/best-practices-rag")


def test_default_target_of_an_unsuffixed_checkout_is_itself() -> None:
    # main() rejects this rather than releasing a repo onto itself.
    dev_root = Path("/home/someone/code/best-practices-rag")

    assert _default_target(dev_root) == dev_root
