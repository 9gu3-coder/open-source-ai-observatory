"""OpenScope AI command-line entry point."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from openscope.github import GitHubClient
from openscope.pipeline import build_offline, run_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscope")
    subcommands = parser.add_subparsers(dest="command", required=True)

    collect = subcommands.add_parser("collect", help="从 GitHub 采集并生成网站数据")
    build = subcommands.add_parser("build", help="从本地历史重新生成网站数据")
    for command in (collect, build):
        command.add_argument("--history", type=Path, default=Path("data/history.json"))
        command.add_argument("--site", type=Path, default=Path("site"))
    collect.add_argument("--config", type=Path, default=Path("config/repos.yaml"))
    build.add_argument("--offline", action="store_true", help="确认不访问网络")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(UTC)
    if args.command == "collect":
        result = run_pipeline(
            args.config,
            args.history,
            args.site,
            GitHubClient(token=os.environ.get("GITHUB_TOKEN")),
            now,
        )
    else:
        if not args.offline:
            raise SystemExit("build 命令必须显式使用 --offline")
        result = build_offline(args.history, args.site, now)
    print(
        f"OpenScope AI：成功 {result.succeeded}，失败 {result.failed}，"
        f"过期回退 {result.stale}；数据 {result.dashboard_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

