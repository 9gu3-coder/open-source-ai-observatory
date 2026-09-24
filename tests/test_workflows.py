from pathlib import Path
from typing import Any, cast

import yaml


def workflow(name: str) -> dict[str, Any]:
    raw = yaml.load(
        Path(f".github/workflows/{name}").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    return cast(dict[str, Any], raw)


def run_commands(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def test_ci_runs_tests_lint_and_offline_build_on_python_312() -> None:
    data = workflow("ci.yml")
    checks = data["jobs"]["checks"]
    commands = "\n".join(run_commands(checks))
    setup = next(
        step
        for step in checks["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )

    assert data["permissions"] == {"contents": "read"}
    assert set(data["on"]) == {"push", "pull_request"}
    assert setup["with"]["python-version"] == "3.12"
    assert "python -m pytest" in commands
    assert "python -m ruff check ." in commands
    assert "python -m openscope.cli build --offline" in commands


def test_update_workflow_has_required_triggers_timezone_and_minimal_permissions() -> None:
    data = workflow("update-pages.yml")
    triggers = data["on"]
    schedule = triggers["schedule"][0]

    assert {"push", "workflow_dispatch", "schedule"} <= set(triggers)
    assert schedule == {"cron": "30 6 * * *", "timezone": "Asia/Shanghai"}
    assert data["permissions"] == {
        "contents": "write",
        "pages": "write",
        "id-token": "write",
    }


def test_collection_failure_blocks_commit_artifact_and_deploy() -> None:
    data = workflow("update-pages.yml")
    update = data["jobs"]["update"]
    steps = update["steps"]
    collect_index = next(index for index, step in enumerate(steps) if step.get("id") == "collect")
    commit_index = next(index for index, step in enumerate(steps) if step.get("id") == "commit")
    artifact_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/upload-pages-artifact@")
    )

    assert "continue-on-error" not in steps[collect_index]
    assert collect_index < commit_index < artifact_index
    assert data["jobs"]["deploy"]["needs"] == "update"
    assert data["jobs"]["deploy"].get("if") in (None, "success()")
