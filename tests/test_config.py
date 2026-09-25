from pathlib import Path

import pytest

from openscope.config import ConfigError, load_repos


def test_load_repos_returns_fifteen_unique_seed_repositories() -> None:
    repos = load_repos(Path("config/repos.yaml"))

    assert len(repos) == 15
    assert len({repo.full_name for repo in repos}) == 15
    assert "lobehub/lobehub" in {repo.full_name for repo in repos}
    assert "Comfy-Org/ComfyUI" in {repo.full_name for repo in repos}
    assert all(getattr(repo, "what_it_is", "") for repo in repos)
    assert all(getattr(repo, "why_use_it", "") for repo in repos)
    assert all(len(getattr(repo, "use_cases", ())) >= 2 for repo in repos)


def test_load_repos_rejects_duplicate_full_names(tmp_path: Path) -> None:
    config = tmp_path / "repos.yaml"
    config.write_text(
        """
- full_name: owner/repo
  display_name: One
  category: 工具
  reason: first
  what_it_is: 一个测试项目
  why_use_it: 用于验证配置
  use_cases: [场景一, 场景二]
- full_name: owner/repo
  display_name: Two
  category: 工具
  reason: duplicate
  what_it_is: 另一个测试项目
  why_use_it: 用于验证重复项
  use_cases: [场景一, 场景二]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="重复.*owner/repo"):
        load_repos(config)


@pytest.mark.parametrize(
    "missing",
    [
        "full_name",
        "display_name",
        "category",
        "reason",
        "what_it_is",
        "why_use_it",
        "use_cases",
    ],
)
def test_load_repos_rejects_missing_required_fields(tmp_path: Path, missing: str) -> None:
    values = {
        "full_name": "owner/repo",
        "display_name": "Repo",
        "category": "工具",
        "reason": "tracked",
        "what_it_is": "一个测试项目",
        "why_use_it": "用于验证配置",
        "use_cases": "\n    - 场景一\n    - 场景二",
    }
    del values[missing]
    config = tmp_path / "repos.yaml"
    config.write_text(
        "\n".join(["- " + next(iter(values)) + ": " + next(iter(values.values()))]
        + [f"  {key}: {value}" for key, value in list(values.items())[1:]]),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=missing):
        load_repos(config)


@pytest.mark.parametrize(
    "use_cases",
    ["单个字符串", "[]", "[只有一个场景]", "[场景一, '']"],
)
def test_load_repos_rejects_use_cases_without_two_nonempty_items(
    tmp_path: Path, use_cases: str
) -> None:
    config = tmp_path / "repos.yaml"
    config.write_text(
        "\n".join(
            [
                "- full_name: owner/repo",
                "  display_name: Repo",
                "  category: 工具",
                "  reason: tracked",
                "  what_it_is: 一个测试项目",
                "  why_use_it: 用于验证配置",
                f"  use_cases: {use_cases}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="use_cases"):
        load_repos(config)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("full_name: owner/repo", "列表"),
        (
            "- full_name: owner/repo\n  display_name: ''\n  category: 工具\n  reason: tracked",
            "display_name",
        ),
        (
            "- full_name: invalid-name\n"
            "  display_name: Repo\n"
            "  category: 工具\n"
            "  reason: tracked\n"
            "  what_it_is: 一个测试项目\n"
            "  why_use_it: 用于验证配置\n"
            "  use_cases: [场景一, 场景二]",
            "full_name",
        ),
        (
            "- full_name: too/many/slashes\n"
            "  display_name: Repo\n"
            "  category: 工具\n"
            "  reason: tracked\n"
            "  what_it_is: 一个测试项目\n"
            "  why_use_it: 用于验证配置\n"
            "  use_cases: [场景一, 场景二]",
            "full_name",
        ),
    ],
)
def test_load_repos_rejects_invalid_shapes(
    tmp_path: Path, content: str, message: str
) -> None:
    config = tmp_path / "repos.yaml"
    config.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_repos(config)
