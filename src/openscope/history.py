"""Bounded repository history and transparent trend scoring."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = 1
MAX_HISTORY_DAYS = 365


class HistoryError(ValueError):
    """Raised when saved history cannot be trusted."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _validate_history(history: object) -> dict[str, Any]:
    if not isinstance(history, dict) or history.get("schema_version") != SCHEMA_VERSION:
        raise HistoryError("历史数据格式或版本无效")
    snapshots = history.get("snapshots")
    if not isinstance(snapshots, list):
        raise HistoryError("历史数据 snapshots 必须是列表")
    seen_dates: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise HistoryError("历史数据快照必须是对象")
        day = snapshot.get("date")
        repos = snapshot.get("repos")
        if not isinstance(day, str) or not day or day in seen_dates:
            raise HistoryError("历史数据日期无效或重复")
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise HistoryError("历史数据日期必须使用 YYYY-MM-DD") from exc
        if not isinstance(repos, dict):
            raise HistoryError("历史数据 repos 必须是对象")
        seen_dates.add(day)
    return cast(dict[str, Any], history)


def load_history(path: Path) -> dict[str, Any] | None:
    """Load validated history, returning None when the file is absent."""

    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryError(f"历史数据无法读取：{exc}") from exc
    return _validate_history(raw)


def update_history(
    existing: dict[str, Any] | None,
    collected: list[dict[str, Any]],
    day: str,
) -> dict[str, Any]:
    """Replace a same-day snapshot, sort dates, and retain the latest year."""

    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise HistoryError("快照日期必须使用 YYYY-MM-DD") from exc

    if existing is None:
        history: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "snapshots": [],
        }
    else:
        history = deepcopy(_validate_history(existing))

    repos: dict[str, dict[str, Any]] = {}
    for record in collected:
        if not isinstance(record, dict):
            raise HistoryError("采集记录必须是对象")
        name = record.get("configured_full_name")
        if not isinstance(name, str) or not name or name in repos:
            raise HistoryError("采集记录 configured_full_name 无效或重复")
        stars = record.get("stars")
        if not isinstance(stars, int) or isinstance(stars, bool) or stars < 0:
            raise HistoryError(f"{name} 的 stars 无效")
        repos[name] = deepcopy(record)

    snapshots = [item for item in history["snapshots"] if item["date"] != day]
    snapshots.append({"date": day, "repos": repos})
    snapshots.sort(key=lambda item: item["date"])
    history["snapshots"] = snapshots[-MAX_HISTORY_DAYS:]
    history["generated_at"] = _utc_now()
    return history


def _timestamp(value: object) -> float:
    if value is None:
        return 0.0
    if not isinstance(value, str):
        raise HistoryError("时间字段必须是 ISO 字符串")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise HistoryError(f"时间字段格式无效：{value}") from exc


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 100.0}
    ordered = sorted(values.items(), key=lambda pair: (pair[1], pair[0]))
    result: dict[str, float] = {}
    index = 0
    denominator = len(ordered) - 1
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_rank = (index + end) / 2
        percentile = average_rank / denominator * 100
        for position in range(index, end + 1):
            result[ordered[position][0]] = percentile
        index = end + 1
    return result


def _baseline_repo(
    snapshots: list[dict[str, Any]], window: int, name: str
) -> dict[str, Any] | None:
    if len(snapshots) < window:
        return None
    candidate = snapshots[-window]["repos"].get(name)
    return candidate if isinstance(candidate, dict) else None


def build_dashboard(history: dict[str, Any] | None) -> dict[str, Any]:
    """Build the browser-facing data model from validated history."""

    if history is None:
        raise HistoryError("历史数据为空")
    checked = _validate_history(history)
    snapshots = sorted(checked["snapshots"], key=lambda item: item["date"])
    if not snapshots:
        raise HistoryError("历史数据没有快照")
    day_count = len(snapshots)
    status = "accumulating" if day_count < 7 else "partial" if day_count < 30 else "ready"
    latest = snapshots[-1]
    repositories: list[dict[str, Any]] = []
    for name, raw_record in latest["repos"].items():
        if not isinstance(raw_record, dict):
            raise HistoryError(f"{name} 的最新记录无效")
        record = deepcopy(raw_record)
        stars = record.get("stars")
        if not isinstance(stars, int) or isinstance(stars, bool):
            raise HistoryError(f"{name} 的 stars 无效")
        base_7 = _baseline_repo(snapshots, 7, name)
        base_30 = _baseline_repo(snapshots, 30, name)
        record["star_delta_7d"] = stars - base_7["stars"] if base_7 else None
        record["star_delta_30d"] = stars - base_30["stars"] if base_30 else None
        record["trend_score"] = None
        record.setdefault("stale", False)
        repositories.append(record)

    if status == "ready":
        by_name = {
            item["configured_full_name"]: item
            for item in repositories
            if isinstance(item["star_delta_7d"], int)
            and isinstance(item["star_delta_30d"], int)
        }
        measures = {
            "delta_7": {name: float(item["star_delta_7d"]) for name, item in by_name.items()},
            "delta_30": {name: float(item["star_delta_30d"]) for name, item in by_name.items()},
            "push": {name: _timestamp(item.get("pushed_at")) for name, item in by_name.items()},
            "release": {
                name: _timestamp(
                    item.get("release", {}).get("published_at")
                    if isinstance(item.get("release"), dict)
                    else None
                )
                for name, item in by_name.items()
            },
            "issues": {
                name: float(
                    sum(
                        issue.get("comments", 0)
                        for issue in item.get("issues", [])
                        if isinstance(issue, dict) and isinstance(issue.get("comments", 0), int)
                    )
                )
                for name, item in by_name.items()
            },
        }
        ranks = {metric: _percentiles(values) for metric, values in measures.items()}
        for name, item in by_name.items():
            item["trend_score"] = round(
                ranks["delta_7"][name] * 0.4
                + ranks["delta_30"][name] * 0.2
                + ranks["push"][name] * 0.2
                + ranks["release"][name] * 0.1
                + ranks["issues"][name] * 0.1,
                1,
            )

    repositories.sort(
        key=lambda item: (
            item["trend_score"] is not None,
            item["trend_score"] if item["trend_score"] is not None else item["stars"],
            item["configured_full_name"],
        ),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": checked.get("generated_at", _utc_now()),
        "latest_date": latest["date"],
        "snapshot_days": day_count,
        "status": status,
        "notice": "热度反映关注与活跃变化，不代表项目质量",
        "repositories": repositories,
    }
