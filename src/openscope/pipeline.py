"""Fault-tolerant collection and static artifact orchestration."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from openscope.config import RepoConfig, load_repos
from openscope.history import build_dashboard, load_history, update_history
from openscope.models import RepoSnapshot
from openscope.report import render_weekly_report

NOTICE = "热度反映关注与活跃变化，不代表项目质量"


class FailureThresholdExceeded(RuntimeError):
    """Raised before any output mutation when more than 20% of repositories fail."""


class RepositoryClient(Protocol):
    def fetch_repo(self, config: RepoConfig) -> RepoSnapshot: ...


@dataclass(frozen=True, slots=True)
class PipelineResult:
    succeeded: int
    failed: int
    stale: int
    dashboard_path: Path
    report_path: Path


def _shanghai_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(ZoneInfo("Asia/Shanghai"))


def _week_name(now: datetime) -> str:
    local = _shanghai_now(now)
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}.md"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _latest_records(history: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not history or not history.get("snapshots"):
        return {}
    latest = max(history["snapshots"], key=lambda item: item["date"])
    return {
        name: deepcopy(record)
        for name, record in latest["repos"].items()
        if isinstance(record, dict)
    }


def _write_outputs(
    history_path: Path,
    site_dir: Path,
    history: dict[str, Any],
    dashboard: dict[str, Any],
    report: str,
    report_name: str,
) -> tuple[Path, Path]:
    dashboard_path = site_dir / "data/dashboard.json"
    report_path = site_dir / "reports" / report_name
    # All render/serialization work happens before replacement; every file replacement is atomic.
    history_text = _json_text(history)
    dashboard_text = _json_text(dashboard)
    _atomic_write(history_path, history_text)
    _atomic_write(dashboard_path, dashboard_text)
    _atomic_write(report_path, report)
    return dashboard_path, report_path


def run_pipeline(
    config_path: Path,
    history_path: Path,
    site_dir: Path,
    client: RepositoryClient,
    now: datetime,
) -> PipelineResult:
    """Collect repositories, apply failure policy, and atomically publish data files."""

    configs = load_repos(config_path)
    existing = load_history(history_path)
    previous = _latest_records(existing)
    collected: list[dict[str, Any]] = []
    failed_names: list[str] = []
    stale_count = 0

    for config in configs:
        try:
            record = client.fetch_repo(config).to_dict()
            record["stale"] = False
            record["stale_reason"] = None
        except Exception as exc:  # A single untrusted remote payload must not stop other repos.
            failed_names.append(config.full_name)
            prior = previous.get(config.full_name)
            if prior is None:
                continue
            record = deepcopy(prior)
            record["stale"] = True
            record["stale_reason"] = type(exc).__name__
            stale_count += 1
        collected.append(record)

    failed_count = len(failed_names)
    if failed_count / len(configs) > 0.20:
        raise FailureThresholdExceeded(
            f"采集失败 {failed_count}/{len(configs)}，超过 20% 阈值；保留上一版网站"
        )

    local_now = _shanghai_now(now)
    history = update_history(existing, collected, local_now.date().isoformat())
    dashboard = build_dashboard(history)
    report_name = _week_name(now)
    dashboard["collection"] = {
        "configured": len(configs),
        "succeeded": len(configs) - failed_count,
        "failed": failed_count,
        "stale": stale_count,
        "failed_repositories": failed_names,
    }
    dashboard["weekly_report"] = {
        "week": report_name.removesuffix(".md"),
        "path": f"reports/{report_name}",
    }
    report = render_weekly_report(dashboard)
    dashboard_path, report_path = _write_outputs(
        history_path, site_dir, history, dashboard, report, report_name
    )
    return PipelineResult(
        succeeded=len(configs) - failed_count,
        failed=failed_count,
        stale=stale_count,
        dashboard_path=dashboard_path,
        report_path=report_path,
    )


def build_offline(history_path: Path, site_dir: Path, now: datetime) -> PipelineResult:
    """Rebuild public artifacts from local history without any network access."""

    history = load_history(history_path)
    if history and history.get("snapshots"):
        dashboard = build_dashboard(history)
    else:
        dashboard = {
            "schema_version": 1,
            "generated_at": history.get("generated_at") if history else None,
            "latest_date": None,
            "snapshot_days": 0,
            "status": "empty",
            "notice": NOTICE,
            "repositories": [],
        }
        history = history or {"schema_version": 1, "generated_at": None, "snapshots": []}
    report_name = _week_name(now)
    dashboard["collection"] = {
        "configured": len(dashboard["repositories"]),
        "succeeded": len(dashboard["repositories"]),
        "failed": 0,
        "stale": sum(bool(item.get("stale")) for item in dashboard["repositories"]),
        "failed_repositories": [],
    }
    dashboard["weekly_report"] = {
        "week": report_name.removesuffix(".md"),
        "path": f"reports/{report_name}",
    }
    report = render_weekly_report(dashboard)
    dashboard_path, report_path = _write_outputs(
        history_path, site_dir, history, dashboard, report, report_name
    )
    return PipelineResult(
        succeeded=len(dashboard["repositories"]),
        failed=0,
        stale=dashboard["collection"]["stale"],
        dashboard_path=dashboard_path,
        report_path=report_path,
    )
