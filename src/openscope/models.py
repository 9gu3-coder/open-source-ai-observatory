"""Serializable domain records used by collection and history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IssueSnapshot:
    number: int
    title: str
    url: str
    comments: int


@dataclass(frozen=True, slots=True)
class ReleaseSnapshot:
    tag_name: str
    name: str
    url: str
    published_at: str


@dataclass(frozen=True, slots=True)
class RepoSnapshot:
    configured_full_name: str
    full_name: str
    display_name: str
    category: str
    reason: str
    source_url: str
    api_url: str
    description: str | None
    stars: int
    forks: int
    open_issues: int
    language: str | None
    license_name: str | None
    pushed_at: str
    release: ReleaseSnapshot | None
    issues: tuple[IssueSnapshot, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return asdict(self)

