from datetime import date, timedelta
from pathlib import Path

import pytest

from openscope.history import (
    HistoryError,
    build_dashboard,
    load_history,
    update_history,
)


def repo(
    name: str,
    stars: int,
    *,
    pushed_at: str = "2026-01-01T00:00:00Z",
    release_at: str | None = None,
    comments: int = 0,
) -> dict[str, object]:
    release = None
    if release_at:
        release = {
            "tag_name": "v1",
            "name": "v1",
            "url": f"https://github.com/{name}/releases/tag/v1",
            "published_at": release_at,
        }
    return {
        "configured_full_name": name,
        "full_name": name,
        "display_name": name,
        "category": "工具",
        "reason": "tracked",
        "source_url": f"https://github.com/{name}",
        "api_url": f"https://api.github.com/repos/{name}",
        "description": "description",
        "stars": stars,
        "forks": 1,
        "open_issues": 1,
        "language": "Python",
        "license_name": "MIT",
        "pushed_at": pushed_at,
        "release": release,
        "issues": [
            {
                "number": 1,
                "title": "Issue",
                "url": f"https://github.com/{name}/issues/1",
                "comments": comments,
            }
        ],
    }


def test_same_day_run_replaces_snapshot() -> None:
    history = update_history(None, [repo("a/a", 1)], "2026-01-01")
    history = update_history(history, [repo("a/a", 2)], "2026-01-01")

    assert len(history["snapshots"]) == 1
    assert history["snapshots"][0]["repos"]["a/a"]["stars"] == 2


def test_history_retains_latest_365_distinct_dates() -> None:
    history = None
    start = date(2025, 1, 1)
    for offset in range(366):
        day = (start + timedelta(days=offset)).isoformat()
        history = update_history(history, [repo("a/a", offset)], day)

    assert history is not None
    assert len(history["snapshots"]) == 365
    assert history["snapshots"][0]["date"] == "2025-01-02"


@pytest.mark.parametrize(
    ("days", "status", "delta_7", "delta_30", "score"),
    [
        (6, "accumulating", None, None, None),
        (7, "partial", 6, None, None),
        (29, "partial", 6, None, None),
        (30, "ready", 6, 29, 100.0),
    ],
)
def test_deltas_and_score_require_enough_distinct_dates(
    days: int,
    status: str,
    delta_7: int | None,
    delta_30: int | None,
    score: float | None,
) -> None:
    history = None
    for offset in range(days):
        history = update_history(
            history,
            [repo("a/a", 100 + offset)],
            (date(2026, 1, 1) + timedelta(days=offset)).isoformat(),
        )

    dashboard = build_dashboard(history)
    item = dashboard["repositories"][0]

    assert dashboard["status"] == status
    assert item["star_delta_7d"] == delta_7
    assert item["star_delta_30d"] == delta_30
    assert item["trend_score"] == score


def test_trend_score_uses_documented_weights() -> None:
    history = None
    start = date(2026, 1, 1)
    for offset in range(30):
        # A gains late: wins only the 7-day metric. B gained earlier and wins all others.
        stars_a = 100 if offset < 24 else 100 + (offset - 23) * 10
        stars_b = 0 if offset == 0 else 100
        history = update_history(
            history,
            [
                repo("a/a", stars_a, pushed_at="2026-01-01T00:00:00Z"),
                repo(
                    "b/b",
                    stars_b,
                    pushed_at="2026-02-01T00:00:00Z",
                    release_at="2026-02-01T00:00:00Z",
                    comments=10,
                ),
            ],
            (start + timedelta(days=offset)).isoformat(),
        )

    items = {
        item["configured_full_name"]: item
        for item in build_dashboard(history)["repositories"]
    }

    assert items["a/a"]["trend_score"] == 40.0
    assert items["b/b"]["trend_score"] == 60.0


def test_invalid_history_json_is_rejected_without_changing_file(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    original = b"{not-json"
    path.write_bytes(original)

    with pytest.raises(HistoryError, match="历史数据"):
        load_history(path)

    assert path.read_bytes() == original


def test_new_repository_accumulates_independently_after_global_history_is_ready() -> None:
    history = None
    start = date(2026, 1, 1)
    for offset in range(30):
        records = [repo("old/old", 100 + offset)]
        if offset == 29:
            records.append(repo("new/new", 10))
        history = update_history(
            history,
            records,
            (start + timedelta(days=offset)).isoformat(),
        )

    first_dashboard = build_dashboard(history)
    first = {
        item["configured_full_name"]: item
        for item in first_dashboard["repositories"]
    }
    assert first_dashboard["status"] == "ready"
    assert first["old/old"]["trend_score"] == 100.0
    assert first["new/new"]["star_delta_7d"] is None
    assert first["new/new"]["star_delta_30d"] is None
    assert first["new/new"]["trend_score"] is None

    for offset in range(30, 59):
        history = update_history(
            history,
            [repo("old/old", 100 + offset), repo("new/new", 10 + offset - 29)],
            (start + timedelta(days=offset)).isoformat(),
        )
    mature = {
        item["configured_full_name"]: item
        for item in build_dashboard(history)["repositories"]
    }
    assert mature["new/new"]["star_delta_30d"] == 29
    assert mature["new/new"]["trend_score"] is not None
