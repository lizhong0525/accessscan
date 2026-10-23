"""Live scanning path: Playwright + axe-core.

This module is imported lazily by the CLI only when a live scan is requested.
Playwright is an OPTIONAL dependency: the core report/baseline logic and the
whole test suite run without it. Install the extras to use this path:

    pip install playwright && playwright install chromium
    npm install axe-core        # provides the axe-core browser bundle

Authentication for local test environments: do NOT hard-code credentials in
config files. Pass a storage state file (created via `playwright codegen` or a
one-off login script) through --storage-state, and keep that file out of
version control (.gitignore covers *.storage-state.json).
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import Issue, parse_axe_result

AXE_INJECT_SCRIPT = "window.axe && axe.run({runOnly:{type:'tag',values:%s}})"


class ScannerError(RuntimeError):
    """Raised when the live scanning path cannot run."""


def _find_axe_source(explicit: str | None) -> str:
    """Locate the axe-core browser bundle without any network access."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("ACCESSSCAN_AXE_SOURCE")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("node_modules") / "axe-core" / "axe.min.js")
    for c in candidates:
        if c.is_file():
            return c.read_text(encoding="utf-8", errors="replace")
    raise ScannerError(
        "axe-core browser bundle not found. Run `npm install axe-core` in the "
        "project directory, or set ACCESSSCAN_AXE_SOURCE / pass --axe-source "
        "pointing at axe.min.js."
    )


def scan_routes(
    base_url: str,
    routes: list[str],
    tags: list[str] | None = None,
    storage_state: str | None = None,
    axe_source: str | None = None,
    screenshot_dir: str | None = None,
    timeout_ms: int = 30000,
) -> tuple[list[Issue], dict[str, str]]:
    """Visit routes in a headless browser and return (issues, screenshots).

    screenshots maps issue fingerprint -> relative screenshot path. Screenshots
    are only captured for nodes with a CSS selector that resolves to exactly
    one visible element.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ScannerError(
            "Playwright is not installed. Live scanning requires the optional "
            "dependencies: `pip install playwright && playwright install "
            "chromium`. Alternatively, replay saved results with --from-file."
        ) from None

    source = _find_axe_source(axe_source)
    run_tags = tags or ["wcag2a", "wcag2aa"]
    issues: list[Issue] = []
    screenshots: dict[str, str] = {}

    import json as _json

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context_args = {}
        if storage_state:
            if not Path(storage_state).is_file():
                browser.close()
                raise ScannerError(f"storage state file not found: {storage_state}")
            context_args["storage_state"] = storage_state
        context = browser.new_context(**context_args)
        page = context.new_page()
        try:
            for route in routes:
                url = base_url.rstrip("/") + "/" + route.lstrip("/")
                try:
                    response = page.goto(url, timeout=timeout_ms)
                except Exception as exc:
                    raise ScannerError(
                        f"failed to load {url}: {exc.__class__.__name__}: {exc}"
                    ) from None
                if response is None:
                    raise ScannerError(f"no response navigating to {url}")
                if response.status >= 400:
                    raise ScannerError(
                        f"HTTP {response.status} navigating to {url}"
                    )
                page.add_script_tag(content=source)
                result = page.evaluate(
                    AXE_INJECT_SCRIPT % _json.dumps(run_tags)
                )
                route_issues = parse_axe_result(result, route)
                if screenshot_dir:
                    screenshots.update(
                        _capture_screenshots(page, route_issues, screenshot_dir, route)
                    )
                issues.extend(route_issues)
        finally:
            browser.close()
    return issues, screenshots


def _capture_screenshots(
    page, route_issues: list[Issue], screenshot_dir: str, route: str
) -> dict[str, str]:
    """Best-effort per-element screenshots; failures never abort a scan."""
    out: dict[str, str] = {}
    safe_route = route.strip("/").replace("/", "_") or "index"
    dest_dir = Path(screenshot_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for index, issue in enumerate(route_issues):
        if issue.selector.startswith("(") or " >> " in issue.selector:
            continue  # iframes / missing selectors: skip
        try:
            locator = page.locator(issue.selector)
            if locator.count() != 1:
                continue
            filename = f"{safe_route}-{index}-{issue.rule_id}.png"
            locator.first.screenshot(path=str(dest_dir / filename))
            out[issue.fingerprint] = f"{Path(screenshot_dir).name}/{filename}"
        except Exception:
            continue
    return out
