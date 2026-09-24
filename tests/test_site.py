import json
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from openscope.history import update_history
from openscope.pipeline import build_offline


class SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.labels: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if values.get("aria-label"):
            self.labels.add(values["aria-label"] or "")


def test_offline_build_preserves_missing_release_and_issue_empty_states(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    site_dir = tmp_path / "site"
    record = {
        "configured_full_name": "owner/repo",
        "full_name": "owner/repo",
        "display_name": "Repo",
        "category": "工具",
        "reason": "tracked",
        "source_url": "https://github.com/owner/repo",
        "api_url": "https://api.github.com/repos/owner/repo",
        "description": None,
        "stars": 1,
        "forks": 0,
        "open_issues": 0,
        "language": None,
        "license_name": None,
        "pushed_at": "2026-09-23T00:00:00Z",
        "release": None,
        "issues": [],
    }
    history = update_history(None, [record], "2026-09-24")
    history_path.write_text(json.dumps(history), encoding="utf-8")

    build_offline(history_path, site_dir, datetime(2026, 9, 24, tzinfo=UTC))
    item = json.loads((site_dir / "data/dashboard.json").read_text())["repositories"][0]

    assert item["release"] is None
    assert item["issues"] == []
    assert item["description"] is None


def test_shipped_site_exposes_required_accessible_surfaces() -> None:
    html = Path("site/index.html").read_text(encoding="utf-8")
    script = Path("site/app.js").read_text(encoding="utf-8")
    parser = SurfaceParser()
    parser.feed(html)

    assert {
        "search-input",
        "category-filter",
        "repo-grid",
        "repo-dialog",
        "release-feed",
        "weekly-report",
    } <= parser.ids
    assert "搜索仓库" in parser.labels
    assert "source_url" in script
    assert "暂无 Release" in script
    assert "暂无高讨论度 Issue" in script
    assert "热度反映关注与活跃变化，不代表项目质量" in html


def test_empty_offline_build_is_idempotent_within_the_same_week(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    site_dir = tmp_path / "site"
    history_path.write_text(
        json.dumps({"schema_version": 1, "generated_at": None, "snapshots": []}),
        encoding="utf-8",
    )

    build_offline(history_path, site_dir, datetime(2026, 9, 24, 0, tzinfo=UTC))
    first = (site_dir / "data/dashboard.json").read_bytes()
    build_offline(history_path, site_dir, datetime(2026, 9, 24, 2, tzinfo=UTC))

    assert (site_dir / "data/dashboard.json").read_bytes() == first
