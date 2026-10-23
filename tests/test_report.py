import json
from pathlib import Path

import pytest

from accessscan.baseline import diff_issues
from accessscan.models import load_axe_file
from accessscan.report import (
    build_html_report,
    build_json_report,
    summarize,
    write_json_report,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "axe-result.bad-page.json"


@pytest.fixture
def issues():
    return load_axe_file(FIXTURE)


def test_summarize(issues):
    s = summarize(issues)
    assert s["violations"] == 7
    assert s["incomplete"] == 1
    assert s["violation_rules"] == 7
    assert s["by_impact"]["critical"] == 2
    assert s["by_impact"]["serious"] == 4
    assert s["by_impact"]["moderate"] == 1


def test_json_report_structure(issues, tmp_path):
    new, existing, fixed = diff_issues(issues, {})
    report = build_json_report(issues, new, existing, fixed)
    assert report["summary"]["new"] == 8
    assert report["summary"]["existing"] == 0
    assert "disclaimer" in report and "NOT WCAG certification" in report["disclaimer"]
    p = tmp_path / "report.json"
    write_json_report(report, p)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["summary"]["violations"] == 7
    first = loaded["new"][0]
    assert {"rule_id", "selector", "fingerprint", "route"} <= set(first)


def test_html_report_contains_issues_and_disclaimer(issues):
    new, existing, fixed = diff_issues(issues, {})
    page = build_html_report(issues, new, existing, fixed)
    assert "image-alt" in page
    assert "needs review" in page  # incomplete bucket rendered
    assert "Not a certification" in page
    assert "lang=\"en\"" in page  # the report itself sets a lang


def test_html_escapes_content():
    from accessscan.models import Issue

    evil = Issue(
        rule_id="xss",
        impact="critical",
        kind="violations",
        route="/<script>",
        selector='<img onerror="alert(1)">',
        html="<img>",
        failure_summary="<b>bad</b>",
        help="help",
        help_url="https://example.com",
    )
    page = build_html_report([evil], [evil], [], [])
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_empty_scan_renders_clean_message():
    page = build_html_report([], [], [], [])
    assert "No issues found" in page
