"""AccessScan command-line interface.

Exit codes: 0 = passed (no failing issues), 1 = failing issues found,
2 = usage or runtime error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .baseline import BaselineError, diff_issues, load_baseline, write_baseline
from .models import AxeResultError, Issue, load_axe_file, sort_issues
from .report import DISCLAIMER, build_html_report, build_json_report, summarize

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2


class ConfigError(ValueError):
    """Raised when the scan configuration file is invalid."""


def _load_config(path: str) -> dict:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {p}") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in config file {p}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"config file {p} must contain a JSON object")
    if not isinstance(data.get("base_url"), str) or not data["base_url"]:
        raise ConfigError(f"config file {p} requires a non-empty 'base_url' string")
    routes = data.get("routes")
    if not isinstance(routes, list) or not routes or not all(
        isinstance(r, str) for r in routes
    ):
        raise ConfigError(f"config file {p} requires a non-empty 'routes' string list")
    tags = data.get("tags", None)
    if tags is not None and not (
        isinstance(tags, list) and all(isinstance(t, str) for t in tags)
    ):
        raise ConfigError(f"'tags' in {p} must be a list of axe-core tag strings")
    return {"base_url": data["base_url"], "routes": routes, "tags": tags}


def _print_summary(
    issues: list[Issue], new: list[Issue], existing: list[Issue], fixed: list[dict]
) -> None:
    s = summarize(issues)
    print(f"Scanned routes: {len({i.route for i in issues}) or 0}")
    print(
        f"Findings: {s['violations']} violations "
        f"({len(new)} new, {len(existing)} known), "
        f"{s['incomplete']} need manual review, {len(fixed)} fixed since baseline"
    )
    for issue in sort_issues(new):
        label = issue.impact or "review"
        print(f"  [NEW] ({label}) {issue.rule_id} @ {issue.route}: {issue.selector}")
    if fixed:
        print("Fixed since baseline:")
        for meta in fixed:
            print(f"  [FIXED] {meta.get('rule_id')} @ {meta.get('route')}")


def _cmd_scan(args: argparse.Namespace) -> int:
    screenshots: dict[str, str] = {}
    try:
        if args.from_file:
            issues = []
            for f in args.from_file:
                issues.extend(load_axe_file(f))
        else:
            if args.config:
                cfg = _load_config(args.config)
                base_url, routes, tags = cfg["base_url"], cfg["routes"], cfg["tags"]
            elif args.url:
                base_url, routes, tags = "", args.url, None
            else:
                raise ConfigError("provide --config, --url, or --from-file")
            from .scanner import ScannerError, scan_routes

            try:
                issues, screenshots = scan_routes(
                    base_url,
                    routes,
                    tags=tags,
                    storage_state=args.storage_state,
                    axe_source=args.axe_source,
                    screenshot_dir=args.screenshot_dir,
                )
            except ScannerError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_ERROR
    except (AxeResultError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    baseline: dict[str, dict] = {}
    if args.baseline:
        try:
            baseline = load_baseline(args.baseline)
        except BaselineError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

    new, existing, fixed = diff_issues(issues, baseline)

    if args.update_baseline:
        if not args.baseline:
            print("error: --update-baseline requires --baseline PATH", file=sys.stderr)
            return EXIT_ERROR
        write_baseline(args.baseline, issues)
        print(f"Baseline updated: {args.baseline} ({len(issues)} findings)")

    if args.json_out:
        report = build_json_report(issues, new, existing, fixed, screenshots)
        try:
            from .report import write_json_report

            write_json_report(report, args.json_out)
        except OSError as exc:
            print(f"error: cannot write JSON report: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"JSON report: {args.json_out}")
    if args.html_out:
        try:
            from .report import write_html_report

            write_html_report(
                build_html_report(issues, new, existing, fixed, screenshots),
                args.html_out,
            )
        except OSError as exc:
            print(f"error: cannot write HTML report: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"HTML report: {args.html_out}")

    _print_summary(issues, new, existing, fixed)
    print(f"\nNote: {DISCLAIMER}")

    if args.fail_on == "none":
        return EXIT_PASS
    if args.fail_on == "any" and issues:
        return EXIT_FAIL
    if args.fail_on == "new" and new:
        return EXIT_FAIL
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="accessscan",
        description="Accessibility smoke-test CLI built on axe-core results.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="scan routes or replay saved axe results")
    src = scan.add_argument_group("input (choose one)")
    src.add_argument("--config", help="JSON config with base_url and routes")
    src.add_argument(
        "--url", action="append", help="full URL to scan (repeatable)"
    )
    src.add_argument(
        "--from-file",
        action="append",
        metavar="AXE_JSON",
        help="replay a saved axe-core JSON result (repeatable); no browser needed",
    )
    live = scan.add_argument_group("live scan options (require Playwright)")
    live.add_argument("--storage-state", help="Playwright storage state JSON for authenticated pages (never commit this file)")
    live.add_argument("--axe-source", help="path to axe-core axe.min.js bundle")
    live.add_argument("--screenshot-dir", help="directory for per-element screenshots (live scans only)")
    out = scan.add_argument_group("output and baseline")
    out.add_argument("--json", dest="json_out", metavar="PATH", help="write JSON report")
    out.add_argument("--html", dest="html_out", metavar="PATH", help="write HTML report")
    out.add_argument("--baseline", metavar="PATH", help="baseline file to compare against")
    out.add_argument(
        "--update-baseline",
        action="store_true",
        help="after scanning, overwrite --baseline with current findings",
    )
    out.add_argument(
        "--fail-on",
        choices=["new", "any", "none"],
        default="new",
        help="exit 1 on: new issues vs baseline (default), any issue, or never",
    )
    scan.set_defaults(func=_cmd_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
