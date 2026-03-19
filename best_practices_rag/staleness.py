import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_AGE_DAYS: int = 90


def load_current_versions(references_dir: Path) -> dict[str, str]:
    text = (references_dir / "tech-versions.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", text, re.MULTILINE)
    return {
        tech.strip().lower(): version.strip()
        for tech, version in rows
        if tech.strip() not in ("Technology", "---", "")
    }


# Returns structured staleness info instead of a bare boolean.
# Keys: is_stale (bool), reason ("version_mismatch"|"max_age"|"no_version_info"|None),
#   stale_technologies (list[str]), fresh_technologies (list[str]),
#   version_deltas (dict[str, dict] — tech -> {stored, current}),
#   document_age_days (int | None)
def check_staleness(
    result: dict[str, Any], current_versions: dict[str, str]
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "is_stale": False,
        "reason": None,
        "stale_technologies": [],
        "fresh_technologies": [],
        "version_deltas": {},
        "document_age_days": None,
    }

    # Compute document age
    synthesized_at = result.get("synthesized_at", "")
    if synthesized_at:
        try:
            synth_dt = datetime.fromisoformat(synthesized_at)
            age_days = (datetime.now(timezone.utc) - synth_dt).days
            info["document_age_days"] = age_days
        except (ValueError, TypeError):
            pass

    # Check tech versions
    raw = result.get("tech_versions_at_synthesis", "")
    if not raw:
        info["is_stale"] = True
        info["reason"] = "no_version_info"
        return info

    try:
        stored: dict[str, str] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        info["is_stale"] = True
        info["reason"] = "no_version_info"
        return info

    for tech, stored_ver in stored.items():
        current_ver: str | None = current_versions.get(tech)
        if current_ver is None:
            # Tech not in versions table — cannot verify staleness, treat as fresh.
            info["fresh_technologies"].append(tech)
        elif current_ver != stored_ver:
            info["stale_technologies"].append(tech)
            info["version_deltas"][tech] = {
                "stored": stored_ver,
                "current": current_ver,
            }
        else:
            info["fresh_technologies"].append(tech)

    if info["stale_technologies"]:
        info["is_stale"] = True
        info["reason"] = "version_mismatch"
        return info

    # Check document age
    if (
        info["document_age_days"] is not None
        and info["document_age_days"] > MAX_AGE_DAYS
    ):
        info["is_stale"] = True
        info["reason"] = "max_age"
        return info

    return info
