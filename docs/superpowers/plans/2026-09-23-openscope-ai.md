# OpenScope AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a zero-cost Chinese dashboard that tracks 15 AI repositories every day.

**Architecture:** A typed Python package reads YAML configuration, fetches GitHub REST data, updates a bounded JSON history, computes transparent percentile scores, and writes a static-site data bundle plus weekly report. A dependency-free browser UI reads that bundle. GitHub Actions runs tests, updates data, commits history, and deploys Pages.

**Tech Stack:** Python 3.12, httpx, PyYAML, pytest, Ruff, HTML, CSS, JavaScript, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-09-23-openscope-ai-design.md`

## Global Constraints

- No paid APIs, user accounts, visitor tracking, custom domain, email, or non-GitHub data sources.
- UI and user documentation are Chinese; code identifiers are English.
- Preserve at most 365 distinct daily snapshots.
- Reuse stale data for isolated failures; abort without data or site mutation when failures exceed 20%.
- Never commit secrets; workflows receive only minimal permissions.
- Test first, observe RED, implement minimally, observe GREEN, then commit each task.

## Review Focus

- GitHub returns a redirect or renamed repository: retain the configured identity while recording the canonical API URL.
- GitHub returns malformed or incomplete JSON: count the repository as failed without corrupting history.
- A scheduled run repeats on the same calendar day: replace that date's snapshot instead of duplicating it.
- Repository count is not divisible by five: reject when `failed / total > 0.20`, not at exactly 20%.
- Browser loads with missing optional release/issue fields: render an explicit empty state without throwing.

## File Map

- `src/openscope/config.py`: YAML configuration validation.
- `src/openscope/github.py`: retrying GitHub API client and payload normalization.
- `src/openscope/history.py`: snapshot persistence, deltas, percentiles, scoring, retention.
- `src/openscope/pipeline.py`: failure threshold, stale fallback, site bundle and weekly report orchestration.
- `src/openscope/cli.py`: collect/build command-line entry point.
- `site/`: static browser application and generated public data.
- `tests/`: unit, integration, and offline build tests.

### Task 1: Project skeleton and validated repository configuration

**Files:**
- Create: `pyproject.toml`, `config/repos.yaml`, `src/openscope/__init__.py`, `src/openscope/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `RepoConfig(full_name: str, display_name: str, category: str, reason: str)` and `load_repos(path: Path) -> list[RepoConfig]`.

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py` with three independent tests: load the shipped file and assert 15 unique `full_name` values; write a temporary YAML file containing a duplicate and assert `ConfigError`; write entries missing each required field and assert `ConfigError` names that field.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL because `openscope.config` does not exist.

- [ ] **Step 3: Implement packaging, strict YAML validation, and the exact 15 verified repository entries**

Use current canonical names `lobehub/lobehub` and `Comfy-Org/ComfyUI`; reject non-list roots, empty strings, duplicates, and names without one `/`.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/test_config.py -q && python -m ruff check .`
Expected: all tests pass and Ruff exits 0.

- [ ] **Step 5: Commit**

Run: `git add pyproject.toml config src tests && git commit -m "feat: add repository configuration"`

### Task 2: Retrying GitHub client and normalized repository records

**Files:**
- Create: `src/openscope/models.py`, `src/openscope/github.py`
- Test: `tests/test_github.py`

**Interfaces:**
- Consumes: `RepoConfig` from Task 1.
- Produces: `GitHubClient.fetch_repo(config) -> RepoSnapshot`, `RepoSnapshot.to_dict() -> dict[str, object]`, and `GitHubAPIError`.

- [ ] **Step 1: Write failing client tests**

Create `tests/test_github.py` using `httpx.MockTransport` with complete GitHub-shaped payloads. Assert normalized metadata, release, and exactly the three highest-comment non-PR issues; release 404 produces `None`; two 429/timeout responses followed by success make exactly three transport requests; response URL/canonical `full_name` after redirect are retained; missing required numeric/string fields raise `GitHubAPIError`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_github.py -q`
Expected: FAIL because `openscope.github` does not exist.

- [ ] **Step 3: Implement the minimal httpx client**

Call repository metadata, latest release, and issues endpoints; exclude items containing `pull_request`; sort issues by comments; retain three. Retry 429, 5xx, transport errors, and timeouts with injectable sleep delays of 1, 2 seconds. Treat release 404 as `None`; validate required payload types.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/test_github.py -q && python -m ruff check .`
Expected: all tests pass and Ruff exits 0.

- [ ] **Step 5: Commit**

Run: `git add src tests && git commit -m "feat: collect GitHub repository data"`

### Task 3: History retention, deltas, scoring, and weekly report

**Files:**
- Create: `src/openscope/history.py`, `src/openscope/report.py`
- Test: `tests/test_history.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: serialized `RepoSnapshot` records.
- Produces: `update_history(existing, collected, date) -> dict`, `build_dashboard(history) -> dict`, and `render_weekly_report(dashboard) -> str`.

- [ ] **Step 1: Write failing history and report tests**

Create literal histories in `tests/test_history.py`: update the same date twice and assert one replaced snapshot; update 366 dates and assert the oldest is removed; assert deltas are absent at 6/29 dates and exact at 7/30 dates; hand-calculate a two-repository percentile example and assert the 40/20/20/10/10 weighted score. In `tests/test_report.py`, assert the Markdown links to repository URLs, contains the heat-not-quality notice, and invalid history input raises before the original file is changed.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_history.py tests/test_report.py -q`
Expected: FAIL because the history and report modules do not exist.

- [ ] **Step 3: Implement bounded history and deterministic ranking**

Use UTC ISO timestamps and an explicit Shanghai calendar date supplied by the caller. Percentile ties receive the same average rank. Before 7 dates, expose `status: accumulating`; between 7 and 29 dates, expose deltas but no full score; at 30 dates expose the weighted score rounded to one decimal.

- [ ] **Step 4: Verify GREEN and lint**

Run: `python -m pytest tests/test_history.py tests/test_report.py -q && python -m ruff check .`
Expected: all tests pass and Ruff exits 0.

- [ ] **Step 5: Commit**

Run: `git add src tests && git commit -m "feat: calculate repository trends"`

### Task 4: Fault-tolerant pipeline and static website

**Files:**
- Create: `src/openscope/pipeline.py`, `src/openscope/cli.py`, `site/index.html`, `site/styles.css`, `site/app.js`, `site/data/dashboard.json`, `data/history.json`
- Test: `tests/test_pipeline.py`, `tests/test_site.py`

**Interfaces:**
- Consumes: Tasks 1-3 interfaces.
- Produces: `run_pipeline(config_path, history_path, site_dir, client, now) -> PipelineResult` and console command `openscope collect`.

- [ ] **Step 1: Write failing pipeline and offline-site tests**

Create a deterministic fake client in `tests/test_pipeline.py`: one failed repository with prior data must publish `stale: true`; 3 failures out of 15 must publish while 4 must raise `FailureThresholdExceeded` and preserve byte-identical output files; a successful run must write schema-valid dashboard JSON and a dated weekly report. In `tests/test_site.py`, run the offline builder with absent release/issues and assert the generated bundle retains explicit empty values, then parse the shipped HTML and assert accessible search, category, details, release, report, and source-link surfaces exist.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_pipeline.py tests/test_site.py -q`
Expected: FAIL because pipeline and site do not exist.

- [ ] **Step 3: Implement atomic orchestration and responsive UI**

Collect every repository independently, use last known snapshot on isolated failure, calculate `failed / total`, and write temporary files followed by atomic replacement only when acceptable. The browser reads only local `data/dashboard.json`; include accessible controls, mobile layout, explicit stale/empty states, source links, and the notice “热度反映关注与活跃变化，不代表项目质量”.

- [ ] **Step 4: Verify GREEN, full suite, lint, and offline build**

Run: `python -m pytest -q && python -m ruff check . && python -m openscope.cli build --offline`
Expected: all tests pass, Ruff exits 0, and offline build exits 0.

- [ ] **Step 5: Commit**

Run: `git add src site data tests && git commit -m "feat: build OpenScope AI dashboard"`

### Task 5: CI, scheduled update, and GitHub Pages deployment

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/update-pages.yml`
- Test: `tests/test_workflows.py`

**Interfaces:**
- Consumes: `openscope collect`, full test command, and `site/` artifact.
- Produces: CI on pull requests/pushes and a Pages workflow on push, manual dispatch, and `06:30 Asia/Shanghai` schedule.

- [ ] **Step 1: Write failing workflow behavior tests**

Parse both workflow YAML files in `tests/test_workflows.py`. Assert CI selects Python 3.12 and executes pytest, Ruff, and offline build; updater exposes push, `workflow_dispatch`, and a 06:30 Shanghai schedule with only the specified permissions; and its dependency graph makes commit/deploy unreachable after a failed collection step.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_workflows.py -q`
Expected: FAIL because workflow files do not exist.

- [ ] **Step 3: Implement workflows**

Use official checkout/setup-python/configure-pages/upload-pages-artifact/deploy-pages actions pinned to stable major versions. Separate collection from deployment; ensure collection failure prevents commit and deploy. Give CI read-only contents; give updater only `contents: write`, `pages: write`, and `id-token: write`.

- [ ] **Step 4: Verify GREEN and full local gates**

Run: `python -m pytest -q && python -m ruff check . && python -m openscope.cli build --offline`
Expected: all tests pass, Ruff exits 0, and offline build exits 0.

- [ ] **Step 5: Commit**

Run: `git add .github tests && git commit -m "ci: automate updates and Pages deployment"`

### Task 6: Beginner documentation, architecture, and final verification

**Files:**
- Create: `README.md`, `docs/architecture.md`, `docs/maintenance.md`, `docs/screenshot.svg`
- Modify: all files only as required by final verified defects.
- Test: full suite and generated artifact checks.

**Interfaces:**
- Consumes: the completed application and workflows.
- Produces: a beginner-readable operating guide and final auditable project.

- [ ] **Step 1: Write documentation and artifact checks**

Add tests that run the real offline build in a temporary directory and assert valid schema version, 15 repository entries, source URLs, no secret-shaped keys, 365-day bound, weekly report path, and required site entry files.

- [ ] **Step 2: Verify RED if the checks expose any missing behavior**

Run: `python -m pytest tests/test_artifacts.py -q`
Expected: FAIL until the final documentation/artifact contract exists.

- [ ] **Step 3: Complete documentation and fix only evidenced gaps**

README covers purpose, screenshots, one-command local setup, configuration edits, manual workflow run, Pages enablement, 60-day scheduled-workflow inactivity behavior, privacy, limitations, and troubleshooting. Architecture documents data flow and failure policy. Maintenance is written for a novice. The SVG is a deterministic screenshot-style preview generated from the shipped visual design, not a claim of a live deployment.

- [ ] **Step 4: Run final verification**

Run: `python -m pytest -q && python -m ruff check . && python -m openscope.cli build --offline && git diff --check`
Expected: all tests pass, Ruff exits 0, build exits 0, and diff check is clean.

- [ ] **Step 5: Commit**

Run: `git add README.md docs tests && git commit -m "docs: add OpenScope AI operating guide"`
