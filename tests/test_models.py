import json
from pathlib import Path

import pytest

from accessscan.models import AxeResultError, Issue, load_axe_file, parse_axe_result

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "axe-result.bad-page.json"


def test_parse_fixture_counts():
    issues = load_axe_file(FIXTURE)
    violations = [i for i in issues if i.kind == "violations"]
    incomplete = [i for i in issues if i.kind == "incomplete"]
    assert len(violations) == 7
    assert len(incomplete) == 1
    assert {i.rule_id for i in violations} == {
        "html-has-lang",
        "document-title",
        "image-alt",
        "label",
        "color-contrast",
        "heading-order",
        "link-name",
    }


def test_route_taken_from_wrapper():
    issues = load_axe_file(FIXTURE)
    assert {i.route for i in issues} == {"/bad-page.html"}


def test_fingerprint_is_stable_and_sensitive():
    issues = load_axe_file(FIXTURE)
    again = load_axe_file(FIXTURE)
    assert [i.fingerprint for i in issues] == [i.fingerprint for i in again]
    a = issues[0]
    moved = Issue(**{**a.__dict__, "route": "/other"})
    assert moved.fingerprint != a.fingerprint


def test_bare_axe_object_accepted(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))["results"]
    p = tmp_path / "bare.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    issues = load_axe_file(p, route="/bare")
    assert len(issues) == 8
    assert all(i.route == "/bare" for i in issues)


def test_missing_file_raises():
    with pytest.raises(AxeResultError, match="not found"):
        load_axe_file("does-not-exist.json")


def test_invalid_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(AxeResultError, match="invalid JSON"):
        load_axe_file(p)


def test_non_object_raises(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(AxeResultError, match="JSON object"):
        load_axe_file(p)


def test_malformed_entry_raises():
    with pytest.raises(AxeResultError, match="missing 'id'"):
        parse_axe_result({"violations": [{"impact": "serious"}]}, "/x")


def test_rule_with_no_nodes_is_kept():
    issues = parse_axe_result(
        {"violations": [{"id": "document-title", "impact": "serious"}]}, "/x"
    )
    assert len(issues) == 1
    assert issues[0].selector == "(no selector)"
