from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .agents import run_agent
from .paths import REPOSITORY_ROOT


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _load_task(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"task_id", "kind", "fixture", "prompt", "checks", "ignore_paths", "allowed_paths", "baseline_expectation"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError(f"task requires fields {sorted(required)}")
    if not isinstance(value["allowed_paths"], list) or not all(isinstance(item, str) for item in value["allowed_paths"]):
        raise ValueError("allowed_paths must be a string array")
    return value


def _check_command(command: list[str]) -> list[str]:
    if os.name != "nt" and len(command) >= 3 and command[:2] == ["cmd", "/c"]:
        return command[2:]
    return command


def _run_checks(task: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    rows = []
    for check in task["checks"]:
        command = _check_command(check["command"])
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command, cwd=workspace, text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=180, check=False,
            )
            row = {"returncode": completed.returncode, "passed": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            row = {"returncode": None, "passed": False, "stdout": "", "stderr": str(exc)}
        row.update({"name": check["name"], "command": command, "elapsed_seconds": time.perf_counter() - started})
        rows.append(row)
    return rows


def _baseline_valid(task: dict[str, Any], checks: list[dict[str, Any]]) -> bool:
    if task["baseline_expectation"] == "passing":
        return bool(checks) and all(row["passed"] for row in checks)
    if task["baseline_expectation"] != "failing":
        return False
    signature = task.get("expected_failure")
    if not isinstance(signature, dict):
        return False
    return any(
        row["name"] == signature.get("check")
        and row["returncode"] == signature.get("returncode")
        and isinstance(signature.get("contains"), str)
        and signature["contains"] in f"{row['stdout']}\n{row['stderr']}"
        for row in checks
    )


def _ignored(relative: str, ignored: list[str]) -> bool:
    normalized = relative.replace("\\", "/")
    return normalized == ".git" or normalized.startswith(".git/") or any(
        normalized == value.rstrip("/") or normalized.startswith(value.rstrip("/") + "/")
        for value in ignored if value.rstrip("/")
    )


def _file_map(root: Path, ignored: list[str]) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not _ignored(path.relative_to(root).as_posix(), ignored)
    }


def _diff(before: dict[str, bytes], after: dict[str, bytes]) -> tuple[dict[str, Any], str]:
    added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    modified = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    lines: list[str] = []
    for name in removed + added + modified:
        try:
            old = before.get(name, b"").decode("utf-8").splitlines(keepends=True)
            new = after.get(name, b"").decode("utf-8").splitlines(keepends=True)
            lines.extend(difflib.unified_diff(old, new, fromfile=f"before/{name}", tofile=f"after/{name}"))
        except UnicodeDecodeError:
            lines.append(f"Binary file changed: {name}\n")
    changed = added + removed + modified
    return {"added": added, "removed": removed, "modified": modified, "changed_paths": changed}, "".join(lines)


def _allowed(path: str, allowed: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == value.rstrip("/") or normalized.startswith(value.rstrip("/") + "/") for value in allowed if value.rstrip("/"))


def run_task(
    task_path: Path,
    output: Path,
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    agent: str = "codex",
    intervention: Path | None = None,
    command_template: str | None = None,
) -> dict[str, Any]:
    task_path, output = task_path.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    task = _load_task(task_path)
    fixtures = (REPOSITORY_ROOT / "fixtures").resolve()
    fixture = (REPOSITORY_ROOT / task["fixture"]).resolve()
    if not fixture.is_relative_to(fixtures) or not fixture.is_dir():
        raise ValueError("task fixture must remain inside fixtures/")
    before, workspace = output / "before", output / "workspace"
    output.mkdir(parents=True)
    shutil.copytree(fixture, before); shutil.copytree(fixture, workspace)
    _write_json(output / "task.json", task)
    baseline = _run_checks(task, before)
    _write_json(output / "checks.before.json", baseline)
    baseline_ok = _baseline_valid(task, baseline)
    if not baseline_ok:
        summary = {"schema_version": "growing-bench-run-1.0", "task_id": task["task_id"], "status": "baseline_invalid", "agent": agent, "baseline_expectation_met": False}
        _write_json(output / "summary.json", summary)
        return summary
    initial = _file_map(before, task["ignore_paths"])
    agent_result = run_agent(agent, task["prompt"], workspace, output / "agent", model, reasoning, timeout, intervention, command_template)
    post = _run_checks(task, workspace)
    _write_json(output / "checks.after.json", post)
    changes, patch = _diff(initial, _file_map(workspace, task["ignore_paths"]))
    _write_json(output / "changes.json", changes)
    (output / "changes.diff").write_text(patch, encoding="utf-8", newline="\n")
    unexpected = [path for path in changes["changed_paths"] if not _allowed(path, task["allowed_paths"])]
    post_ok = bool(post) and all(row["passed"] for row in post)
    status = "completed" if agent_result["status"] == "completed" and post_ok and not unexpected else "failed"
    final = (output / "agent" / "final.md").read_text(encoding="utf-8")
    events = [
        {"event_id": f"{task['task_id']}::user", "kind": "user", "content": task["prompt"]},
        {"event_id": f"{task['task_id']}::assistant", "kind": "assistant", "content": final},
    ]
    if patch:
        events.append({"event_id": f"{task['task_id']}::diff", "kind": "artifact", "content": patch})
    with (output / "trajectory.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "schema_version": "growing-bench-run-1.0", "task_id": task["task_id"],
        "kind": task["kind"], "status": status, "agent": agent, "model": model,
        "intervention": str(intervention) if intervention else None,
        "baseline_expectation_met": baseline_ok, "post_checks_passed": post_ok,
        "allowed_paths_ok": not unexpected, "unexpected_changed_paths": unexpected,
        "changes": changes, "agent_result": agent_result,
        "artifacts": {"trajectory": "trajectory.jsonl", "final": "agent/final.md", "raw_stdout": "agent/stdout.log", "raw_stderr": "agent/stderr.log", "diff": "changes.diff", "workspace": "workspace"},
    }
    _write_json(output / "summary.json", summary)
    return summary
