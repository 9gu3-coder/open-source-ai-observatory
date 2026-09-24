import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from openscope.config import load_repos
from openscope.pipeline import build_offline


def record(full_name: str, display_name: str, category: str, stars: int) -> dict[str, Any]:
    return {
        "configured_full_name": full_name,
        "full_name": full_name,
        "display_name": display_name,
        "category": category,
        "reason": "tracked",
        "source_url": f"https://github.com/{full_name}",
        "api_url": f"https://api.github.com/repos/{full_name}",
        "description": "Public repository",
        "stars": stars,
        "forks": 1,
        "open_issues": 1,
        "language": "Python",
        "license_name": "MIT",
        "pushed_at": "2026-09-23T00:00:00Z",
        "release": None,
        "issues": [],
        "stale": False,
    }


def secret_shaped_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in {"token", "secret", "password", "api_key", "private_key"}:
                found.add(key)
            found |= secret_shaped_keys(child)
    elif isinstance(value, list):
        for child in value:
            found |= secret_shaped_keys(child)
    return found


def test_real_offline_builder_emits_complete_bounded_public_artifact(tmp_path: Path) -> None:
    repos = load_repos(Path("config/repos.yaml"))
    start = date(2025, 9, 25)
    snapshots = []
    for offset in range(365):
        snapshots.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "repos": {
                    repo.full_name: record(
                        repo.full_name,
                        repo.display_name,
                        repo.category,
                        100 + offset,
                    )
                    for repo in repos
                },
            }
        )
    history_path = tmp_path / "history.json"
    history_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-09-24T00:00:00Z",
                "snapshots": snapshots,
            }
        ),
        encoding="utf-8",
    )

    result = build_offline(
        history_path,
        tmp_path / "site",
        datetime(2026, 9, 24, tzinfo=UTC),
    )
    dashboard = json.loads(result.dashboard_path.read_text(encoding="utf-8"))

    assert dashboard["schema_version"] == 1
    assert dashboard["snapshot_days"] == 365
    assert len(dashboard["repositories"]) == 15
    assert all(
        item["source_url"].startswith("https://github.com/")
        for item in dashboard["repositories"]
    )
    assert dashboard["weekly_report"]["path"] == "reports/2026-W39.md"
    assert result.report_path.exists()
    assert secret_shaped_keys(dashboard) == set()


def test_required_site_and_beginner_documentation_are_shipped() -> None:
    for required in [
        "site/index.html",
        "site/styles.css",
        "site/app.js",
        "README.md",
        "docs/architecture.md",
        "docs/maintenance.md",
        "docs/screenshot.svg",
    ]:
        assert Path(required).is_file(), required

    readme = Path("README.md").read_text(encoding="utf-8")
    for topic in [
        "本地运行",
        "修改追踪清单",
        "手动运行",
        "GitHub Pages",
        "60 天",
        "隐私",
        "限制",
        "故障排查",
    ]:
        assert topic in readme
