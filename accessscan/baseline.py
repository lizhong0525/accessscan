"""Baseline support: remember known issues so only NEW ones fail CI.

A baseline is a JSON file listing fingerprints (rule + route + selector) of
issues the team has accepted for now. A scan compares its findings against the
baseline and splits them into three buckets:

- new:      findings not in the baseline  -> these fail the build
- existing: findings also in the baseline -> reported, but tolerated
- fixed:    baseline entries no longer found -> good news, prune with
            ``--update-baseline``
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Issue


class BaselineError(ValueError):
    """Raised when a baseline file is malformed."""


BASELINE_VERSION = 1


def load_baseline(path: str | Path) -> dict[str, dict]:
    """Load a baseline file into {fingerprint: metadata}.

    A missing file is treated as an empty baseline (first run). A malformed
    file is a hard error: silently ignoring it would let old violations
    masquerade as new ones, which defeats the purpose.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BaselineError(f"baseline file {p} is not valid UTF-8: {exc}") from None
    except OSError as exc:
        raise BaselineError(f"cannot read baseline file {p}: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"invalid JSON in baseline file {p}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise BaselineError(
            f"baseline file {p} must be an object with an 'issues' list; "
            "delete it and regenerate with --update-baseline if it is stale"
        )
    baseline: dict[str, dict] = {}
    for entry in data["issues"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("fingerprint"), str):
            raise BaselineError(f"malformed entry in baseline file {p}")
        baseline[entry["fingerprint"]] = entry
    return baseline


def diff_issues(
    issues: list[Issue], baseline: dict[str, dict]
) -> tuple[list[Issue], list[Issue], list[dict]]:
    """Split current findings into (new, existing, fixed) against a baseline."""
    new, existing = [], []
    seen: set[str] = set()
    for issue in issues:
        if issue.fingerprint in baseline:
            existing.append(issue)
            seen.add(issue.fingerprint)
        else:
            new.append(issue)
    fixed = [meta for fp, meta in baseline.items() if fp not in seen]
    return new, existing, fixed


def write_baseline(path: str | Path, issues: list[Issue]) -> None:
    """Write current findings as the new baseline (overwrites existing)."""
    p = Path(path)
    entries = [
        {
            "fingerprint": issue.fingerprint,
            "rule_id": issue.rule_id,
            "route": issue.route,
            "selector": issue.selector,
            "impact": issue.impact,
            "kind": issue.kind,
        }
        for issue in issues
    ]
    entries.sort(key=lambda e: e["fingerprint"])
    payload = {
        "version": BASELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "issues": entries,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
