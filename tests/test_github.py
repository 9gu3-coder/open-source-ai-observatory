from collections.abc import Callable

import httpx
import pytest

from openscope.config import RepoConfig
from openscope.github import GitHubAPIError, GitHubClient

REPO = RepoConfig("owner/repo", "Repo", "工具", "观察理由")


def metadata(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "full_name": "owner/repo",
        "html_url": "https://github.com/owner/repo",
        "url": "https://api.github.com/repos/owner/repo",
        "description": "A useful repository",
        "stargazers_count": 120,
        "forks_count": 14,
        "open_issues_count": 7,
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-09-23T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def release() -> dict[str, object]:
    return {
        "tag_name": "v1.2.0",
        "name": "Version 1.2",
        "html_url": "https://github.com/owner/repo/releases/tag/v1.2.0",
        "published_at": "2026-09-20T08:00:00Z",
    }


def issue(number: int, comments: int, *, pull_request: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "number": number,
        "title": f"Issue {number}",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "comments": comments,
    }
    if pull_request:
        payload["pull_request"] = {"url": "https://api.github.com/pulls/1"}
    return payload


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> GitHubClient:
    return GitHubClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_repo_normalizes_metadata_release_and_top_three_issues() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json=release(), request=request)
        if request.url.path.endswith("/issues"):
            items = [issue(1, 2), issue(2, 9), issue(3, 5), issue(4, 12, pull_request=True)]
            return httpx.Response(200, json=items, request=request)
        return httpx.Response(200, json=metadata(), request=request)

    snapshot = client_for(handler).fetch_repo(REPO)

    assert snapshot.configured_full_name == "owner/repo"
    assert snapshot.full_name == "owner/repo"
    assert snapshot.stars == 120
    assert snapshot.license_name == "MIT"
    assert snapshot.release is not None
    assert snapshot.release.tag_name == "v1.2.0"
    assert [item.number for item in snapshot.issues] == [2, 3, 1]
    assert snapshot.to_dict()["source_url"] == "https://github.com/owner/repo"


def test_missing_latest_release_is_not_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404, json={"message": "Not Found"}, request=request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        return httpx.Response(200, json=metadata(), request=request)

    assert client_for(handler).fetch_repo(REPO).release is None


@pytest.mark.parametrize("failure", ["rate-limit", "timeout"])
def test_transient_failures_retry_three_attempts(failure: str) -> None:
    metadata_attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal metadata_attempts
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404, request=request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        metadata_attempts += 1
        if metadata_attempts < 3:
            if failure == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json=metadata(), request=request)

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GitHubClient(client=raw_client, sleep=delays.append).fetch_repo(REPO)

    assert result.stars == 120
    assert metadata_attempts == 3
    assert delays == [1.0, 2.0]


def test_canonical_identity_is_recorded_after_repository_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404, request=request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        canonical = metadata(
            full_name="new-owner/new-repo",
            html_url="https://github.com/new-owner/new-repo",
            url="https://api.github.com/repos/new-owner/new-repo",
        )
        return httpx.Response(200, json=canonical, request=request)

    snapshot = client_for(handler).fetch_repo(REPO)

    assert snapshot.configured_full_name == "owner/repo"
    assert snapshot.full_name == "new-owner/new-repo"
    assert snapshot.api_url == "https://api.github.com/repos/new-owner/new-repo"


@pytest.mark.parametrize(
    "broken",
    [
        {"stargazers_count": "many"},
        {"stargazers_count": -1},
        {"forks_count": -1},
        {"open_issues_count": -1},
        {"full_name": None},
        {"license": "MIT"},
        {"pushed_at": 123},
        {"pushed_at": "not-a-timestamp"},
    ],
)
def test_malformed_required_payload_raises_github_api_error(broken: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404, request=request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        return httpx.Response(200, json=metadata(**broken), request=request)

    with pytest.raises(GitHubAPIError, match="响应格式"):
        client_for(handler).fetch_repo(REPO)


def test_malformed_release_timestamp_raises_github_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            broken = release()
            broken["published_at"] = "yesterday"
            return httpx.Response(200, json=broken, request=request)
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], request=request)
        return httpx.Response(200, json=metadata(), request=request)

    with pytest.raises(GitHubAPIError, match="published_at"):
        client_for(handler).fetch_repo(REPO)


def test_issue_collection_follows_pagination_until_three_non_pull_requests() -> None:
    requested_pages: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404, request=request)
        if request.url.path.endswith("/issues"):
            requested_pages.append(request.url.params.get("page"))
            if request.url.params.get("page") == "2":
                return httpx.Response(
                    200,
                    json=[issue(21, 30), issue(22, 20), issue(23, 10)],
                    request=request,
                )
            next_url = "https://api.github.com/repos/owner/repo/issues?page=2"
            return httpx.Response(
                200,
                json=[issue(number, 100 - number, pull_request=True) for number in range(1, 21)],
                headers={"Link": f'<{next_url}>; rel="next"'},
                request=request,
            )
        return httpx.Response(200, json=metadata(), request=request)

    snapshot = client_for(handler).fetch_repo(REPO)

    assert requested_pages == [None, "2"]
    assert [item.number for item in snapshot.issues] == [21, 22, 23]
