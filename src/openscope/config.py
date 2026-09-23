"""Repository-list configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when repository configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class RepoConfig:
    full_name: str
    display_name: str
    category: str
    reason: str


_REQUIRED_FIELDS = ("full_name", "display_name", "category", "reason")


def _required_text(entry: dict[str, Any], field: str, index: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"第 {index + 1} 项的 {field} 必须是非空字符串")
    return value.strip()


def load_repos(path: Path) -> list[RepoConfig]:
    """Load and validate the repository watch list at *path*."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"无法读取仓库配置：{exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise ConfigError("仓库配置根节点必须是非空列表")

    repos: list[RepoConfig] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"第 {index + 1} 项必须是对象")
        values = {field: _required_text(item, field, index) for field in _REQUIRED_FIELDS}
        full_name = values["full_name"]
        parts = full_name.split("/")
        if len(parts) != 2 or not all(parts):
            raise ConfigError(f"第 {index + 1} 项的 full_name 必须使用 owner/repo 格式")
        if full_name in seen:
            raise ConfigError(f"重复的仓库 full_name：{full_name}")
        seen.add(full_name)
        repos.append(RepoConfig(**values))

    return repos

