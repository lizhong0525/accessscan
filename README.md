# AccessScan

Accessibility smoke-test CLI for teams who want an early, honest signal: it runs axe-core against your routes and fails CI only on **newly introduced** issues, without pretending a green run means WCAG conformance.

## Quickstart

```bash
python -m accessscan scan --from-file fixtures/axe-result.bad-page.json --json report.json --html report.html
```

That replays a saved axe-core scan of the included broken fixture page — no browser, no install, works offline. Exit code is `1` because new violations were found.

## Demo walkthrough (2 minutes, no browser needed)

`fixtures/bad-page.html` is a page with deliberately planted issues (missing `lang`, missing `<title>`, image without `alt`, unlabeled input, low contrast, skipped heading level, empty link). `fixtures/axe-result.bad-page.json` is the axe-core result for it.

```bash
# 1. Scan: 7 violations + 1 "needs review" are reported, exit code 1
python -m accessscan scan --from-file fixtures/axe-result.bad-page.json --json report.json --html report.html

# 2. Accept the current state as the baseline
python -m accessscan scan --from-file fixtures/axe-result.bad-page.json --baseline baseline.json --update-baseline

# 3. Same scan now passes — known issues are tolerated, exit code 0
python -m accessscan scan --from-file fixtures/axe-result.bad-page.json --baseline baseline.json

# 4. Introduce a new violation (or fix one) and re-run: only the delta fails the build
```

Open `report.html` to see issues grouped as new/known, with impact badges, CSS selectors, and links to the axe rule documentation.

## Live scanning (optional, requires Playwright)

AccessScan never implements its own accessibility rules — live scans inject the real [axe-core](https://github.com/dequelabs/axe-core) engine into pages via Playwright:

```bash
pip install playwright && playwright install chromium
npm install axe-core   # provides node_modules/axe-core/axe.min.js

python -m accessscan scan --config fixtures/accessscan.config.json \
    --screenshot-dir screenshots --json report.json --html report.html \
    --baseline baseline.json
```

The config file lists `base_url` and `routes`; each route is visited headlessly, axe-core runs inside the page, and each offending element gets a CSS selector plus a best-effort screenshot.

### Authenticated local test environments

Never put credentials in the config file or the repository. Create a Playwright **storage state** once (via `playwright codegen --save-storage=local.storage-state.json <url>` or a one-off login script), keep the file out of git (`.gitignore` already covers `*.storage-state.json`), and pass it at runtime:

```bash
python -m accessscan scan --config accessscan.config.json --storage-state local.storage-state.json
```

In CI, inject the storage state from your secret store as a file or environment-provided artifact; do not commit it.

## Features

- axe-core engine (via Playwright) as the live path; `--from-file` replays saved results offline
- Collects violations *and* incomplete ("needs review") checks, with selectors and optional element screenshots
- JSON + self-contained HTML reports
- Baseline file: known issues stop failing CI; only new issues (or regressions) do; fixed issues are reported
- CI-friendly exit codes: `0` pass, `1` failing issues, `2` usage/runtime error (`--fail-on new|any|none`)
- Pure-stdlib core; the test suite runs with no browser, no network, no extra installs

## What a green run means

A passing AccessScan report is **not** WCAG certification and not a statement of conformance. Automated engines like axe-core catch only a subset of issues (commonly cited as roughly a third of WCAG success criteria). You still need manual keyboard-only navigation and screen-reader testing. AccessScan tells you this on every run, by design.

## Development

```bash
python -m pytest -q   # 32 tests, offline, no browser
```

## Known limitations

- Live scans require Playwright + a local axe-core bundle; there is no bundled browser or CDN fetch (by design, to stay offline-friendly)
- Screenshots are live-scan-only and skipped for elements inside iframes
- Baselines key on rule + route + CSS selector; a redesign that changes selectors makes old entries look "fixed" and their findings "new"
- axe "incomplete" results are reported but never fail the build on their own (they need human judgment)

## Roadmap

- Diff view between two saved reports (`accessscan diff a.json b.json`)
- Auto-prune fixed entries on `--update-baseline` with an interactive accept flow
- SARIF output for GitHub code scanning annotations

## License

MIT — see [LICENSE](LICENSE).
