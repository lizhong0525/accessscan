import json
from pathlib import Path

import pytest

from accessscan.cli import EXIT_ERROR, EXIT_FAIL, EXIT_PASS, main

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "axe-result.bad-page.json"


def test_from_file_scan_fails_with_new_issues(tmp_path, capsys):
    rc = main(["scan", "--from-file", str(FIXTURE)])
    out = capsys.readouterr().out
    assert rc == EXIT_FAIL
    assert "8 new" in out
    assert "[NEW]" in out
    assert "NOT WCAG certification" in out


def test_reports_written(tmp_path):
    json_out = tmp_path / "out" / "report.json"
    html_out = tmp_path / "out" / "report.html"
    rc = main(
        ["scan", "--from-file", str(FIXTURE), "--json", str(json_out),
         "--html", str(html_out)]
    )
    assert rc == EXIT_FAIL
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["summary"]["violations"] == 7
    assert "image-alt" in html_out.read_text(encoding="utf-8")


def test_baseline_then_rescan_passes(tmp_path):
    bl = tmp_path / "baseline.json"
    rc1 = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl),
                "--update-baseline"])
    assert rc1 == EXIT_FAIL  # first run: everything is new
    assert bl.exists()
    rc2 = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl)])
    assert rc2 == EXIT_PASS


def test_fail_on_none_always_passes():
    rc = main(["scan", "--from-file", str(FIXTURE), "--fail-on", "none"])
    assert rc == EXIT_PASS


def test_fail_on_any_fails_even_with_baseline(tmp_path):
    bl = tmp_path / "baseline.json"
    main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl),
          "--update-baseline"])
    rc = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl),
               "--fail-on", "any"])
    assert rc == EXIT_FAIL


def test_missing_input_file_is_error(capsys):
    rc = main(["scan", "--from-file", "nope.json"])
    err = capsys.readouterr().err
    assert rc == EXIT_ERROR
    assert "not found" in err


def test_malformed_input_file_is_error(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{broken", encoding="utf-8")
    rc = main(["scan", "--from-file", str(p)])
    assert rc == EXIT_ERROR
    assert "invalid JSON" in capsys.readouterr().err


def test_malformed_baseline_is_error(tmp_path, capsys):
    bl = tmp_path / "bl.json"
    bl.write_text('{"nope": true}', encoding="utf-8")
    rc = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl)])
    assert rc == EXIT_ERROR
    assert "'issues' list" in capsys.readouterr().err


def test_update_baseline_requires_baseline_path(capsys):
    rc = main(["scan", "--from-file", str(FIXTURE), "--update-baseline"])
    assert rc == EXIT_ERROR
    assert "requires --baseline" in capsys.readouterr().err


def test_no_input_source_is_error(capsys):
    rc = main(["scan"])
    assert rc == EXIT_ERROR
    assert "provide --config" in capsys.readouterr().err


def test_malformed_config_is_error(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"base_url": "http://x"}', encoding="utf-8")  # missing routes
    rc = main(["scan", "--config", str(cfg)])
    assert rc == EXIT_ERROR
    assert "routes" in capsys.readouterr().err


def test_live_scan_without_playwright_fails_gracefully(tmp_path, capsys):
    """Live path must error cleanly, never crash, when deps are missing."""
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        json.dumps({"base_url": "http://localhost:1", "routes": ["/"]}),
        encoding="utf-8",
    )
    rc = main(["scan", "--config", str(cfg)])
    captured = capsys.readouterr()
    # Either playwright is missing (error message) or it is installed and the
    # connection is refused / axe-core bundle missing; all are EXIT_ERROR.
    assert rc == EXIT_ERROR
    assert "error" in captured.err.lower() or rc == EXIT_ERROR
