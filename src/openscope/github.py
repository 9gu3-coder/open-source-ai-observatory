"""Small, retrying GitHub REST API client."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Never, cast

import httpx

from openscope.config import RepoConfig
from openscope.models import IssueSnapshot, ReleaseSnapshot, RepoSnapshot


class GitHubAPIError(RuntimeError):
    """Raised when GitHub cannot provide a valid repository record."""


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OpenScope-AI/0.1",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(headers=headers, timeout=20, follow_redirects=True)
        self._headers = headers if client is not None else None
        self._sleep = sleep

    def _request(self, url: str, *, allow_404: bool = False) -> httpx.Response | None:
        for attempt in range(3):
            try:
                response = self._client.get(
                    url,
                    headers=self._headers,
                    follow_redirects=True,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 2:
                    raise GitHubAPIError(f"GitHub 请求失败：{url}") from exc
                self._sleep(float(2**attempt))
                continue

            if allow_404 and response.status_code == 404:
                return None
            rate_limited = response.status_code == 429 or (
                response.status_code == 403
                and response.headers.get("X-RateLimit-Remaining") == "0"
            )
            if rate_limited or response.status_code >= 500:
                if attempt == 2:
                    raise GitHubAPIError(
                        f"GitHub 暂时不可用：{response.status_code} {url}"
                    )
                self._sleep(float(2**attempt))
                continue
            if response.is_error:
                raise GitHubAPIError(f"GitHub 返回 {response.status_code}：{url}")
            return response
        raise AssertionError("unreachable")

    @staticmethod
    def _json(response: httpx.Response, expected: type[Any]) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAPIError("GitHub 响应格式无效：不是 JSON") from exc
        if not isinstance(payload, expected):
            raise GitHubAPIError("GitHub 响应格式无效：结构不匹配")
        return payload

    @staticmethod
    def _bad(field: str) -> Never:
        raise GitHubAPIError(f"GitHub 响应格式无效：{field}")

    @classmethod
    def _text(cls, payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        return value if isinstance(value, str) and value else cls._bad(field)

    @classmethod
    def _integer(cls, payload: dict[str, Any], field: str) -> int:
        value = payload.get(field)
        return value if isinstance(value, int) and not isinstance(value, bool) else cls._bad(field)

    @classmethod
    def _nonnegative_integer(cls, payload: dict[str, Any], field: str) -> int:
        value = cls._integer(payload, field)
        return value if value >= 0 else cls._bad(field)

    @classmethod
    def _positive_integer(cls, payload: dict[str, Any], field: str) -> int:
        value = cls._integer(payload, field)
        return value if value > 0 else cls._bad(field)

    @classmethod
    def _timestamp_text(cls, payload: dict[str, Any], field: str) -> str:
        value = cls._text(payload, field)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return cls._bad(field)
        if parsed.tzinfo is None:
            return cls._bad(field)
        return value

    def _parse_release(self, response: httpx.Response | None) -> ReleaseSnapshot | None:
        if response is None:
            return None
        payload = cast(dict[str, Any], self._json(response, dict))
        name = payload.get("name")
        if name is None:
            name = self._text(payload, "tag_name")
        if not isinstance(name, str):
            self._bad("release.name")
        return ReleaseSnapshot(
            tag_name=self._text(payload, "tag_name"),
            name=name,
            url=self._text(payload, "html_url"),
            published_at=self._timestamp_text(payload, "published_at"),
        )

    def _parse_issue_page(self, response: httpx.Response) -> list[IssueSnapshot]:
        raw_items = cast(list[Any], self._json(response, list))
        issues: list[IssueSnapshot] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                self._bad("issues[]")
            item = cast(dict[str, Any], raw)
            if "pull_request" in item:
                continue
            issues.append(
                IssueSnapshot(
                    number=self._positive_integer(item, "number"),
                    title=self._text(item, "title"),
                    url=self._text(item, "html_url"),
                    comments=self._nonnegative_integer(item, "comments"),
                )
            )
        return issues

    def _fetch_issues(self, url: str) -> tuple[IssueSnapshot, ...]:
        issues: dict[int, IssueSnapshot] = {}
        visited: set[str] = set()
        next_url: str | None = url
        for _ in range(10):
            if next_url is None or next_url in visited or len(issues) >= 3:
                break
            visited.add(next_url)
            response = self._request(next_url)
            assert response is not None
            for issue in self._parse_issue_page(response):
                issues[issue.number] = issue
            next_link = response.links.get("next")
            next_url = next_link.get("url") if next_link else None
        ordered = sorted(issues.values(), key=lambda item: (-item.comments, item.number))
        return tuple(ordered[:3])

    def fetch_repo(self, config: RepoConfig) -> RepoSnapshot:
        """Fetch and normalize one configured repository."""

        base = f"https://api.github.com/repos/{config.full_name}"
        metadata_response = self._request(base)
        assert metadata_response is not None
        payload = cast(dict[str, Any], self._json(metadata_response, dict))

        license_payload = payload.get("license")
        if license_payload is not None and not isinstance(license_payload, dict):
            self._bad("license")
        license_name: str | None = None
        if isinstance(license_payload, dict):
            raw_license = license_payload.get("spdx_id")
            if raw_license is not None and not isinstance(raw_license, str):
                self._bad("license.spdx_id")
            license_name = raw_license

        description = payload.get("description")
        language = payload.get("language")
        if description is not None and not isinstance(description, str):
            self._bad("description")
        if language is not None and not isinstance(language, str):
            self._bad("language")

        release_response = self._request(f"{base}/releases/latest", allow_404=True)
        issues = self._fetch_issues(
            f"{base}/issues?state=open&sort=comments&direction=desc&per_page=100"
        )

        return RepoSnapshot(
            configured_full_name=config.full_name,
            full_name=self._text(payload, "full_name"),
            display_name=config.display_name,
            category=config.category,
            reason=config.reason,
            source_url=self._text(payload, "html_url"),
            api_url=self._text(payload, "url"),
            description=description,
            stars=self._nonnegative_integer(payload, "stargazers_count"),
            forks=self._nonnegative_integer(payload, "forks_count"),
            open_issues=self._nonnegative_integer(payload, "open_issues_count"),
            language=language,
            license_name=license_name,
            pushed_at=self._timestamp_text(payload, "pushed_at"),
            release=self._parse_release(release_response),
            issues=issues,
        )
