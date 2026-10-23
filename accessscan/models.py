"""Data model and axe-core result parsing.

AccessScan does not invent its own accessibility rules. It consumes results
produced by axe-core (https://github.com/dequelabs/axe-core), either live via
Playwright or from a previously saved axe JSON result file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

IMPACT_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, None: 4}

# axe result buckets we surface to the user. "incomplete" means axe could not
# decide automatically and a human must review the node.
RESULT_KINDS = ("violations", "incomplete")


class AxeResultError(ValueError):
    """Raised when an axe result file is missing or malformed."""


@dataclass(frozen=True)
class Issue:
    """A single rule/node finding reported by axe-core."""

    rule_id: str
    impact: str | None
    kind: str  # "violations" or "incomplete"
    route: str
    selector: str
    html: str
    failure_summary: str
    help: str
    help_url: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fingerprint(self) -> str:
        """Stable identity used for baseline comparisons.

        Same rule + same route + same CSS selector => same finding, regardless
        of run time or node ordering.
        """
        raw = f"{self.rule_id}|{self.route}|{self.selector}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _selector_from_node(node: dict) -> str:
    target = node.get("target")
    if isinstance(target, list):
        # axe targets may be nested (iframe paths); flatten to a readable form.
        parts = []
        for part in target:
            parts.append(" >> ".join(part) if isinstance(part, list) else str(part))
        return " >> ".join(parts)
    if isinstance(target, str):
        return target
    return "(no selector)"


def parse_axe_result(data: dict, route: str) -> list[Issue]:
    """Convert one axe-core results object into a flat list of Issues."""
    if not isinstance(data, dict):
        raise AxeResultError("axe result must be a JSON object")
    issues: list[Issue] = []
    for kind in RESULT_KINDS:
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            raise AxeResultError(f"axe result field '{kind}' must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or "id" not in entry:
                raise AxeResultError(
                    f"malformed axe entry in '{kind}': missing 'id'"
                )
            nodes = entry.get("nodes") or []
            if not nodes:
                # A rule-level finding with no nodes (rare); keep it visible.
                nodes = [{}]
            for node in nodes:
                if not isinstance(node, dict):
                    raise AxeResultError(
                        f"malformed node in rule '{entry['id']}'"
                    )
                issues.append(
                    Issue(
                        rule_id=str(entry["id"]),
                        impact=entry.get("impact"),
                        kind=kind,
                        route=route,
                        selector=_selector_from_node(node),
                        html=str(node.get("html") or ""),
                        failure_summary=str(node.get("failureSummary") or ""),
                        help=str(entry.get("help") or ""),
                        help_url=str(entry.get("helpUrl") or ""),
                        tags=tuple(str(t) for t in entry.get("tags") or ()),
                    )
                )
    return issues


def load_axe_file(path: str | Path, route: str | None = None) -> list[Issue]:
    """Load a saved axe-core JSON result from disk.

    The file may be a bare axe results object, or an object with a top-level
    ``results`` key plus an optional ``route`` label (the format the live
    scanner writes per route).
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AxeResultError(f"axe result file not found: {p}") from None
    except UnicodeDecodeError as exc:
        raise AxeResultError(f"axe result file {p} is not valid UTF-8: {exc}") from None
    except OSError as exc:
        raise AxeResultError(f"cannot read axe result file {p}: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AxeResultError(f"invalid JSON in axe result file {p}: {exc}") from None
    if not isinstance(data, dict):
        raise AxeResultError(f"axe result file {p} must contain a JSON object")
    effective_route = route or str(data.get("route") or p.stem)
    results = data.get("results", data)
    return parse_axe_result(results, effective_route)


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Deterministic ordering: violations before incomplete, then impact."""
    return sorted(
        issues,
        key=lambda i: (
            RESULT_KINDS.index(i.kind),
            IMPACT_ORDER.get(i.impact, 4),
            i.rule_id,
            i.route,
            i.selector,
        ),
    )
