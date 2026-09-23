from pathlib import Path

import pytest

from openscope.config import ConfigError, load_repos


def test_load_repos_returns_fifteen_unique_seed_repositories() -> None:
    repos = load_repos(Path("config/repos.yaml"))

    assert len(repos) == 15
    assert len({repo.full_name for repo in repos}) == 15
    assert "lobehub/lobehub" in {repo.full_name for repo in repos}
    assert "Comfy-Org/ComfyUI" in {repo.full_name for repo in repos}


def test_load_repos_rejects_duplicate_full_names(tmp_path: Path) -> None:
    config = tmp_path / "repos.yaml"
    config.write_text(
        """
- full_name: owner/repo
  display_name: One
  category: 工具
  reason: first
- full_name: owner/repo
  display_name: Two
  category: 工具
  reason: duplicate
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="重复.*owner/repo"):
        load_repos(config)


@pytest.mark.parametrize("missing", ["full_name", "display_name", "category", "reason"])
def test_load_repos_rejects_missing_required_fields(tmp_path: Path, missing: str) -> None:
    values = {
        "full_name": "owner/repo",
        "display_name": "Repo",
        "category": "工具",
        "reason": "tracked",
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
    ("content", "message"),
    [
        ("full_name: owner/repo", "列表"),
        (
            "- full_name: owner/repo\n  display_name: ''\n  category: 工具\n  reason: tracked",
            "display_name",
        ),
        (
            "- full_name: invalid-name\n  display_name: Repo\n  category: 工具\n  reason: tracked",
            "full_name",
        ),
        (
            "- full_name: too/many/slashes\n"
            "  display_name: Repo\n"
            "  category: 工具\n"
            "  reason: tracked",
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
