"""JSON and HTML report generation from parsed issues."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import IMPACT_ORDER, Issue, sort_issues

DISCLAIMER = (
    "Automated accessibility checks catch only a subset of WCAG issues. "
    "A passing AccessScan report is NOT WCAG certification or a statement of "
    "conformance. Manual keyboard-only navigation and screen-reader testing "
    "remain required."
)


def summarize(issues: list[Issue]) -> dict:
    """Count issues by kind and impact."""
    violations = [i for i in issues if i.kind == "violations"]
    incomplete = [i for i in issues if i.kind == "incomplete"]
    by_impact: dict[str, int] = {}
    for i in violations:
        key = i.impact or "unknown"
        by_impact[key] = by_impact.get(key, 0) + 1
    return {
        "violations": len(violations),
        "incomplete": len(incomplete),
        "violation_rules": len({i.rule_id for i in violations}),
        "by_impact": dict(
            sorted(by_impact.items(), key=lambda kv: IMPACT_ORDER.get(kv[0], 4))
        ),
    }


def _issue_to_dict(issue: Issue, screenshot: str | None = None) -> dict:
    d = {
        "rule_id": issue.rule_id,
        "impact": issue.impact,
        "kind": issue.kind,
        "route": issue.route,
        "selector": issue.selector,
        "html": issue.html,
        "failure_summary": issue.failure_summary,
        "help": issue.help,
        "help_url": issue.help_url,
        "tags": list(issue.tags),
        "fingerprint": issue.fingerprint,
    }
    if screenshot:
        d["screenshot"] = screenshot
    return d


def build_json_report(
    issues: list[Issue],
    new: list[Issue],
    existing: list[Issue],
    fixed: list[dict],
    screenshots: dict[str, str] | None = None,
) -> dict:
    screenshots = screenshots or {}
    return {
        "tool": "accessscan",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            **summarize(issues),
            "new": len(new),
            "existing": len(existing),
            "fixed": len(fixed),
        },
        "new": [
            _issue_to_dict(i, screenshots.get(i.fingerprint)) for i in sort_issues(new)
        ],
        "existing": [
            _issue_to_dict(i, screenshots.get(i.fingerprint))
            for i in sort_issues(existing)
        ],
        "fixed": fixed,
        "disclaimer": DISCLAIMER,
    }


def write_json_report(report: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


_IMPACT_COLORS = {
    "critical": "#b3261e",
    "serious": "#d94f04",
    "moderate": "#b8860b",
    "minor": "#5b6770",
}

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AccessScan report</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; color: #1a1a1a; }}
 h1 {{ font-size: 1.4rem; }}
 table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }}
 th, td {{ border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top; }}
 th {{ background: #f5f5f5; }}
 code {{ background: #f5f5f5; padding: .1rem .3rem; border-radius: 3px; font-size: .85em; }}
 .badge {{ color: #fff; border-radius: 3px; padding: .1rem .4rem; font-size: .8em; white-space: nowrap; }}
 .incomplete .badge {{ background: #5b6770; }}
 .summary span {{ margin-right: 1rem; }}
 .disclaimer {{ border-left: 4px solid #b8860b; background: #fdf6e3; padding: .8rem 1rem; margin-top: 2rem; }}
 img.shot {{ max-width: 220px; border: 1px solid #ddd; display: block; margin-top: .3rem; }}
</style>
</head>
<body>
<h1>AccessScan accessibility smoke-test report</h1>
<p>Generated {generated} &middot; {routes}</p>
<p class="summary">{summary}</p>
{sections}
<div class="disclaimer"><strong>Not a certification.</strong> {disclaimer}</div>
</body>
</html>
"""


def _badge(issue: Issue) -> str:
    if issue.kind == "incomplete":
        return '<span class="badge">needs review</span>'
    color = _IMPACT_COLORS.get(issue.impact or "", "#5b6770")
    label = html.escape(issue.impact or "unknown")
    return f'<span class="badge" style="background:{color}">{label}</span>'


def _section(title: str, issues: list[Issue], screenshots: dict[str, str]) -> str:
    if not issues:
        return ""
    rows = []
    for i in sort_issues(issues):
        shot = screenshots.get(i.fingerprint)
        shot_html = (
            f'<img class="shot" src="{html.escape(shot)}" alt="screenshot of element">'
            if shot
            else ""
        )
        cls = ' class="incomplete"' if i.kind == "incomplete" else ""
        rows.append(
            f"<tr{cls}><td>{_badge(i)}</td>"
            f"<td><code>{html.escape(i.rule_id)}</code></td>"
            f"<td>{html.escape(i.route)}</td>"
            f"<td><code>{html.escape(i.selector)}</code>{shot_html}</td>"
            f"<td>{html.escape(i.help)} "
            f'<a href="{html.escape(i.help_url)}">rule docs</a><br>'
            f"<small>{html.escape(i.failure_summary)}</small></td></tr>"
        )
    return (
        f"<h2>{html.escape(title)} ({len(issues)})</h2>"
        "<table><tr><th>Impact</th><th>Rule</th><th>Route</th>"
        "<th>Element</th><th>Details</th></tr>" + "".join(rows) + "</table>"
    )


def build_html_report(
    issues: list[Issue],
    new: list[Issue],
    existing: list[Issue],
    fixed: list[dict],
    screenshots: dict[str, str] | None = None,
) -> str:
    screenshots = screenshots or {}
    s = summarize(issues)
    routes = ", ".join(sorted({i.route for i in issues})) or "(no routes)"
    summary_bits = [
        f"<strong>{s['violations']}</strong> violations",
        f"<strong>{s['incomplete']}</strong> needs review",
        f"<strong>{len(new)}</strong> new",
        f"<strong>{len(existing)}</strong> known (baselined)",
        f"<strong>{len(fixed)}</strong> fixed since baseline",
    ]
    for impact, count in s["by_impact"].items():
        color = _IMPACT_COLORS.get(impact, "#5b6770")
        summary_bits.append(
            f'<span class="badge" style="background:{color}">'
            f"{html.escape(impact)}: {count}</span>"
        )
    sections = (
        _section("New issues", new, screenshots)
        + _section("Known issues (in baseline)", existing, screenshots)
    )
    if not sections:
        sections = "<p>No issues found. Nice.</p>"
    return _PAGE.format(
        generated=html.escape(datetime.now(timezone.utc).isoformat(timespec="seconds")),
        routes=html.escape(routes),
        summary=" ".join(f"<span>{b}</span>" for b in summary_bits),
        sections=sections,
        disclaimer=html.escape(DISCLAIMER),
    )


def write_html_report(html_text: str, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_text, encoding="utf-8")
