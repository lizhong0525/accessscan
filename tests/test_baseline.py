from pathlib import Path

import pytest

from accessscan.baseline import (
    BaselineError,
    diff_issues,
    load_baseline,
    write_baseline,
)
from accessscan.models import load_axe_file

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "axe-result.bad-page.json"


@pytest.fixture
def issues():
    return load_axe_file(FIXTURE)


def test_missing_baseline_is_empty(tmp_path):
    assert load_baseline(tmp_path / "none.json") == {}


def test_roundtrip_no_new_issues(tmp_path, issues):
    bl = tmp_path / "baseline.json"
    write_baseline(bl, issues)
    new, existing, fixed = diff_issues(issues, load_baseline(bl))
    assert new == []
    assert len(existing) == len(issues)
    assert fixed == []


def test_new_issue_detected(tmp_path, issues):
    write_baseline(tmp_path / "bl.json", issues[:-1])
    baseline = load_baseline(tmp_path / "bl.json")
    new, existing, fixed = diff_issues(issues, baseline)
    assert new == [issues[-1]]
    assert len(existing) == len(issues) - 1
    assert fixed == []


def test_fixed_issue_detected(tmp_path, issues):
    write_baseline(tmp_path / "bl.json", issues)
    current = issues[:-1]
    new, existing, fixed = diff_issues(current, load_baseline(tmp_path / "bl.json"))
    assert new == []
    assert len(existing) == len(current)
    assert len(fixed) == 1
    assert fixed[0]["rule_id"] == issues[-1].rule_id


def test_malformed_baseline_raises(tmp_path):
    p = tmp_path / "bl.json"
    p.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(BaselineError, match="'issues' list"):
        load_baseline(p)


def test_invalid_json_baseline_raises(tmp_path):
    p = tmp_path / "bl.json"
    p.write_text("oops", encoding="utf-8")
    with pytest.raises(BaselineError, match="invalid JSON"):
        load_baseline(p)
