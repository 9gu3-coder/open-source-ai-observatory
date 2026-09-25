import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from openscope.config import RepoConfig, load_repos
from openscope.github import GitHubClient
from openscope.history import update_history
from openscope.models import RepoSnapshot
from openscope.pipeline import FailureThresholdExceeded, run_pipeline

NOW = datetime(2026, 9, 24, 0, 0, tzinfo=UTC)


def snapshot(config: RepoConfig, stars: int = 100) -> RepoSnapshot:
    return RepoSnapshot(
        configured_full_name=config.full_name,
        full_name=config.full_name,
        display_name=config.display_name,
        category=config.category,
        reason=config.reason,
        source_url=f"https://github.com/{config.full_name}",
        api_url=f"https://api.github.com/repos/{config.full_name}",
        description="A repository",
        stars=stars,
        forks=10,
        open_issues=5,
        language="Python",
        license_name="MIT",
        pushed_at="2026-09-23T00:00:00Z",
        release=None,
        issues=(),
    )


class FakeClient:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()

    def fetch_repo(self, config: RepoConfig) -> RepoSnapshot:
        if config.full_name in self.failures:
            raise RuntimeError("simulated failure")
        return snapshot(config, stars=200)


def write_prior_history(path: Path, repos: list[RepoConfig]) -> None:
    history = update_history(
        None,
        [snapshot(config).to_dict() for config in repos],
        "2026-09-23",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


def test_one_failure_reuses_last_record_and_marks_stale(tmp_path: Path) -> None:
    repos = load_repos(Path("config/repos.yaml"))
    history_path = tmp_path / "data/history.json"
    site_dir = tmp_path / "site"
    write_prior_history(history_path, repos)

    result = run_pipeline(
        Path("config/repos.yaml"),
        history_path,
        site_dir,
        FakeClient({repos[0].full_name}),
        NOW,
    )
    dashboard = json.loads((site_dir / "data/dashboard.json").read_text(encoding="utf-8"))
    by_name = {item["configured_full_name"]: item for item in dashboard["repositories"]}

    assert result.failed == 1
    assert result.stale == 1
    assert len(by_name) == 15
    assert by_name[repos[0].full_name]["stale"] is True
    assert by_name[repos[0].full_name]["stars"] == 100


def test_twenty_percent_failures_publish_but_more_abort_without_changes(
    tmp_path: Path,
) -> None:
    repos = load_repos(Path("config/repos.yaml"))
    history_path = tmp_path / "data/history.json"
    site_dir = tmp_path / "site"
    write_prior_history(history_path, repos)

    result = run_pipeline(
        Path("config/repos.yaml"),
        history_path,
        site_dir,
        FakeClient({repo.full_name for repo in repos[:3]}),
        NOW,
    )
    assert result.failed == 3

    old_history = history_path.read_bytes()
    old_dashboard = (site_dir / "data/dashboard.json").read_bytes()
    with pytest.raises(FailureThresholdExceeded, match="4/15"):
        run_pipeline(
            Path("config/repos.yaml"),
            history_path,
            site_dir,
            FakeClient({repo.full_name for repo in repos[:4]}),
            NOW,
        )

    assert history_path.read_bytes() == old_history
    assert (site_dir / "data/dashboard.json").read_bytes() == old_dashboard


def test_successful_pipeline_writes_dashboard_and_weekly_report(tmp_path: Path) -> None:
    history_path = tmp_path / "data/history.json"
    site_dir = tmp_path / "site"

    result = run_pipeline(
        Path("config/repos.yaml"), history_path, site_dir, FakeClient(), NOW
    )
    dashboard = json.loads(result.dashboard_path.read_text(encoding="utf-8"))

    assert dashboard["schema_version"] == 1
    assert dashboard["latest_date"] == "2026-09-24"
    assert len(dashboard["repositories"]) == 15
    assert all(
        item["source_url"].startswith("https://github.com/")
        for item in dashboard["repositories"]
    )
    assert result.report_path.name == "2026-W39.md"
    assert "OpenScope AI 周报" in result.report_path.read_text(encoding="utf-8")


def test_malformed_github_timestamp_becomes_stale_repository_failure(tmp_path: Path) -> None:
    repos = load_repos(Path("config/repos.yaml"))
    broken_name = repos[0].full_name
    history_path = tmp_path / "data/history.json"
    site_dir = tmp_path / "site"
    write_prior_history(history_path, repos)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/releases/latest"):
            return httpx.Response(404, request=request)
        if path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        parts = path.strip("/").split("/")
        full_name = "/".join(parts[1:3])
        config = next(item for item in repos if item.full_name == full_name)
        payload = snapshot(config, stars=200).to_dict()
        payload.update(
            {
                "html_url": payload.pop("source_url"),
                "url": payload.pop("api_url"),
                "stargazers_count": payload.pop("stars"),
                "forks_count": payload.pop("forks"),
                "open_issues_count": payload.pop("open_issues"),
                "license": {"spdx_id": payload.pop("license_name")},
            }
        )
        if full_name == broken_name:
            payload["pushed_at"] = "invalid-time"
        return httpx.Response(200, json=payload, request=request)

    client = GitHubClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = run_pipeline(
        Path("config/repos.yaml"), history_path, site_dir, client, NOW
    )
    dashboard = json.loads((site_dir / "data/dashboard.json").read_text(encoding="utf-8"))
    by_name = {item["configured_full_name"]: item for item in dashboard["repositories"]}

    assert result.failed == 1
    assert result.stale == 1
    assert by_name[broken_name]["stale"] is True
