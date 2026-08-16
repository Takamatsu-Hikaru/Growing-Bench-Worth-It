from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import REPOSITORY_ROOT


TASK_KINDS = {"code", "writing", "internal_review", "external_peer_review"}
CRITERION_KINDS = {"check", "file_exists", "file_contains", "json_field", "semantic"}


def load_task(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_task(value)
    return value


def validate_task(task: dict[str, Any]) -> None:
    required = {
        "task_id", "kind", "fixture", "prompt", "checks", "ignore_paths",
        "allowed_paths", "baseline_expectation",
    }
    if not isinstance(task, dict) or not required.issubset(task):
        raise ValueError(f"task requires fields {sorted(required)}")
    if task["kind"] not in TASK_KINDS:
        raise ValueError(f"unsupported task kind {task['kind']!r}")
    for name in ("ignore_paths", "allowed_paths"):
        if not isinstance(task[name], list) or not all(isinstance(item, str) for item in task[name]):
            raise ValueError(f"{name} must be a string array")
    forbidden = task.get("forbidden_paths", [])
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise ValueError("forbidden_paths must be a string array")
    artifacts = task.get("required_artifacts", [])
    if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
        raise ValueError("required_artifacts must be a string array")
    if task["baseline_expectation"] not in {"passing", "failing"}:
        raise ValueError("baseline_expectation must be passing or failing")
    if not isinstance(task["checks"], list) or not task["checks"]:
        raise ValueError("checks must be a nonempty array")
    names: set[str] = set()
    for check in task["checks"]:
        if not isinstance(check, dict) or not isinstance(check.get("name"), str):
            raise ValueError("each check requires a name")
        command = check.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise ValueError(f"check {check.get('name')!r} requires a command array")
        if check["name"] in names:
            raise ValueError(f"duplicate check name {check['name']!r}")
        names.add(check["name"])
    if task["baseline_expectation"] == "failing":
        signature = task.get("expected_failure")
        if not isinstance(signature, dict) or not {
            "check", "returncode", "contains"
        }.issubset(signature):
            raise ValueError("a failing baseline requires an exact expected_failure")
    criteria = task.get("completion_criteria", [])
    if criteria and not isinstance(criteria, list):
        raise ValueError("completion_criteria must be an array")
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        if isinstance(criterion, str):
            continue  # v1 living tasks remain readable during migration.
        if not isinstance(criterion, dict):
            raise ValueError(f"completion_criteria[{index}] must be an object")
        criterion_id = criterion.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise ValueError(f"completion_criteria[{index}] requires criterion_id")
        if criterion_id in seen:
            raise ValueError(f"duplicate criterion_id {criterion_id!r}")
        seen.add(criterion_id)
        if criterion.get("kind") not in CRITERION_KINDS:
            raise ValueError(f"criterion {criterion_id!r} has an invalid kind")


def resolve_fixture(task_path: Path, task: dict[str, Any]) -> Path:
    raw = Path(task["fixture"])
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("fixture must be a relative path without parent traversal")
    if raw.parts and raw.parts[0] == "fixtures":
        fixture = (REPOSITORY_ROOT / raw).resolve()
        allowed_root = (REPOSITORY_ROOT / "fixtures").resolve()
    else:
        fixture = (task_path.parent / raw).resolve()
        allowed_root = task_path.parent.resolve()
    if not fixture.is_relative_to(allowed_root) or not fixture.is_dir():
        raise ValueError("task fixture is missing or outside its allowed root")
    return fixture


def _workspace_path(workspace: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"workspace path must remain relative: {relative!r}")
    resolved = (workspace / value).resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        raise ValueError(f"workspace path escapes fixture: {relative!r}")
    return resolved


def _field(value: Any, dotted: str) -> Any:
    current = value
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted)
    return current


def evaluate_completion(
    task: dict[str, Any], workspace: Path, checks: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool, bool]:
    check_map = {row["name"]: row for row in checks}
    results: list[dict[str, Any]] = []
    machine_passed = True
    semantic_pending = False

    for path in task.get("required_artifacts", []):
        passed = _workspace_path(workspace, path).is_file()
        results.append({
            "criterion_id": f"artifact:{path}", "kind": "file_exists",
            "description": f"Required artifact exists: {path}", "status": "passed" if passed else "failed",
        })
        machine_passed = machine_passed and passed

    for index, criterion in enumerate(task.get("completion_criteria", [])):
        if isinstance(criterion, str):
            results.append({
                "criterion_id": f"legacy-semantic-{index + 1}", "kind": "semantic",
                "description": criterion, "status": "pending",
            })
            semantic_pending = True
            continue
        criterion_id = criterion["criterion_id"]
        kind = criterion["kind"]
        passed = False
        if kind == "semantic":
            semantic_pending = True
            status = "pending"
        elif kind == "check":
            row = check_map.get(criterion.get("check"))
            passed = bool(row and row.get("passed"))
            status = "passed" if passed else "failed"
        elif kind == "file_exists":
            passed = _workspace_path(workspace, criterion["path"]).is_file()
            status = "passed" if passed else "failed"
        elif kind == "file_contains":
            path = _workspace_path(workspace, criterion["path"])
            passed = path.is_file() and criterion["contains"] in path.read_text(encoding="utf-8")
            status = "passed" if passed else "failed"
        else:
            path = _workspace_path(workspace, criterion["path"])
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                passed = _field(value, criterion["field"]) == criterion.get("equals")
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                passed = False
            status = "passed" if passed else "failed"
        if status == "failed":
            machine_passed = False
        results.append({
            "criterion_id": criterion_id, "kind": kind,
            "description": criterion.get("description", criterion_id), "status": status,
        })
    return results, machine_passed, semantic_pending

