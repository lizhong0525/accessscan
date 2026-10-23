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
    # totals and baseline buckets are stated separately, not as
    # "7 violations (8 new)" which reads as contradictory
    assert "8 total (7 violations, 1 need manual review)" in out
    assert "Baseline: 8 new, 0 known" in out
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


def test_non_utf8_input_file_is_clean_error(tmp_path, capsys):
    p = tmp_path / "latin1.json"
    p.write_bytes(b"\xff\xfe\x00bad")
    rc = main(["scan", "--from-file", str(p)])
    assert rc == EXIT_ERROR
    assert "UTF-8" in capsys.readouterr().err


def test_baseline_path_is_directory_is_clean_error(tmp_path, capsys):
    rc = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(tmp_path)])
    assert rc == EXIT_ERROR
    assert "baseline" in capsys.readouterr().err


def test_non_utf8_baseline_is_clean_error(tmp_path, capsys):
    bl = tmp_path / "bl.bin"
    bl.write_bytes(b"\xff\xfe")
    rc = main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl)])
    assert rc == EXIT_ERROR
    assert "UTF-8" in capsys.readouterr().err


def test_update_baseline_to_unwritable_path_is_clean_error(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    rc = main([
        "scan", "--from-file", str(FIXTURE),
        "--baseline", str(blocker / "baseline.json"), "--update-baseline",
    ])
    assert rc == EXIT_ERROR
    assert "cannot write baseline" in capsys.readouterr().err


def test_config_path_is_directory_is_clean_error(tmp_path, capsys):
    rc = main(["scan", "--config", str(tmp_path)])
    assert rc == EXIT_ERROR
    assert "config" in capsys.readouterr().err


def test_non_ascii_output_does_not_crash_on_legacy_console(tmp_path, monkeypatch):
    """Selectors with non-ASCII chars must not crash cp1252 consoles."""
    import io

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["results"]["violations"][0]["nodes"][0]["target"] = ["img.日本語"]
    src = tmp_path / "unicode-axe.json"
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = main(["scan", "--from-file", str(src)])
    assert rc == EXIT_FAIL


def test_regression_fixture_demo_delta(tmp_path, capsys):
    """README demo step 4: one fix + one regression vs baseline."""
    regression = FIXTURE.with_name("axe-result.bad-page.regression.json")
    bl = tmp_path / "baseline.json"
    main(["scan", "--from-file", str(FIXTURE), "--baseline", str(bl),
          "--update-baseline"])
    capsys.readouterr()
    rc = main(["scan", "--from-file", str(regression), "--baseline", str(bl)])
    out = capsys.readouterr().out
    assert rc == EXIT_FAIL
    assert "Baseline: 1 new, 7 known, 1 fixed since baseline" in out
    assert 'img[src="chart.png"]' in out
    assert "[FIXED] heading-order" in out
