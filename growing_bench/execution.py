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
from .quality import isolation_profile, validate_isolation
from .task_contract import evaluate_completion, load_task, resolve_fixture
from .trajectory import utc_now


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _check_command(command: list[str]) -> list[str]:
    if os.name != "nt" and len(command) >= 3 and command[:2] == ["cmd", "/c"]:
        return command[2:]
    return command


def _run_checks(task: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    rows = []
    for check in task["checks"]:
        command = _check_command(check["command"])
        started_at = utc_now()
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command, cwd=workspace, text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=float(check.get("timeout_seconds", 180)), check=False,
            )
            row = {
                "returncode": completed.returncode, "passed": completed.returncode == 0,
                "stdout": completed.stdout, "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            row = {
                "returncode": None, "passed": False, "stdout": exc.stdout or "",
                "stderr": exc.stderr or "", "timed_out": True,
            }
        except OSError as exc:
            row = {"returncode": None, "passed": False, "stdout": "", "stderr": str(exc)}
        row.update({
            "name": check["name"], "command": command, "started_at": started_at,
            "finished_at": utc_now(), "elapsed_seconds": time.perf_counter() - started,
        })
        rows.append(row)
    return rows


def _baseline_valid(task: dict[str, Any], checks: list[dict[str, Any]]) -> bool:
    if task["baseline_expectation"] == "passing":
        return bool(checks) and all(row["passed"] for row in checks)
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


def _under(path: str, roots: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        normalized == value.rstrip("/") or normalized.startswith(value.rstrip("/") + "/")
        for value in roots if value.rstrip("/")
    )


def _check_event_kind(command: list[str]) -> str:
    value = " ".join(command).casefold()
    if any(token in value for token in ("pdflatex", "latexmk", "tectonic")):
        return "compile_result"
    return "test_result"


def _trajectory_events(
    task: dict[str, Any], agent_result: dict[str, Any], post: list[dict[str, Any]], patch: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{
        "event_id": f"{task['task_id']}::user", "kind": "user",
        "timestamp": agent_result.get("started_at") or utc_now(), "duration_ms": None,
        "tool": None, "target": None, "status": "success", "content": task["prompt"],
        "visible_output": None, "usage": None, "source_adapter": "runner",
        "source_event_type": "task_prompt",
    }]
    for index, raw in enumerate(agent_result.get("visible_events", []), start=1):
        event = dict(raw)
        event["event_id"] = f"{task['task_id']}::agent::{index:04d}"
        events.append(event)
    final_path = agent_result.get("artifacts", {}).get("final")
    events.append({
        "event_id": f"{task['task_id']}::final", "kind": "final",
        "timestamp": agent_result.get("finished_at") or utc_now(), "duration_ms": None,
        "tool": None, "target": final_path, "status": "success" if agent_result.get("status") == "completed" else "failure",
        "content": None, "visible_output": None, "usage": agent_result.get("usage"),
        "source_adapter": agent_result.get("agent", "runner"), "source_event_type": "final_response",
    })
    for index, row in enumerate(post, start=1):
        events.append({
            "event_id": f"{task['task_id']}::post-check::{index:02d}",
            "kind": _check_event_kind(row["command"]), "timestamp": row["finished_at"],
            "duration_ms": row["elapsed_seconds"] * 1000.0, "tool": "runner-check",
            "target": row["name"], "status": "success" if row["passed"] else "failure",
            "content": " ".join(row["command"]),
            "visible_output": f"{row['stdout']}\n{row['stderr']}".strip(), "usage": None,
            "source_adapter": "runner", "source_event_type": "post_check",
        })
    if patch:
        events.append({
            "event_id": f"{task['task_id']}::diff", "kind": "diff", "timestamp": utc_now(),
            "duration_ms": None, "tool": "runner-diff", "target": "changes.diff", "status": "success",
            "content": patch, "visible_output": None, "usage": None,
            "source_adapter": "runner", "source_event_type": "workspace_diff",
        })
    return events


def run_task(
    task_path: Path,
    output: Path,
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    agent: str = "codex",
    intervention: Path | None = None,
    command_template: str | None = None,
    isolation: str = "copy",
) -> dict[str, Any]:
    validate_isolation(agent, isolation)
    total_started = time.perf_counter()
    task_path, output = task_path.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    task = load_task(task_path)
    fixture = resolve_fixture(task_path, task)
    before, workspace = output / "before", output / "workspace"
    output.mkdir(parents=True)
    shutil.copytree(fixture, before)
    shutil.copytree(fixture, workspace)
    _write_json(output / "task.json", task)
    baseline = _run_checks(task, before)
    _write_json(output / "checks.before.json", baseline)
    baseline_ok = _baseline_valid(task, baseline)
    if not baseline_ok:
        summary = {
            "schema_version": "growing-bench-run-2.0", "task_id": task["task_id"],
            "status": "baseline_invalid", "agent": agent, "baseline_expectation_met": False,
            "post_checks_passed": False, "allowed_paths_ok": True,
            "machine_completion_passed": False, "semantic_completion_pending": False,
            "elapsed_seconds": time.perf_counter() - total_started, "criterion_results": [],
            "artifacts": {"before_checks": "checks.before.json"},
        }
        _write_json(output / "summary.json", summary)
        return summary
    initial = _file_map(before, task["ignore_paths"])
    agent_result = run_agent(
        agent, task["prompt"], workspace, output / "agent", model, reasoning,
        timeout, intervention, command_template,
    )
    post = _run_checks(task, workspace)
    _write_json(output / "checks.after.json", post)
    changes, patch = _diff(initial, _file_map(workspace, task["ignore_paths"]))
    _write_json(output / "changes.json", changes)
    (output / "changes.diff").write_text(patch, encoding="utf-8", newline="\n")
    forbidden = task.get("forbidden_paths", [])
    unexpected = [
        path for path in changes["changed_paths"]
        if not _under(path, task["allowed_paths"]) or _under(path, forbidden)
    ]
    post_ok = bool(post) and all(row["passed"] for row in post)
    criterion_results, machine_ok, semantic_pending = evaluate_completion(task, workspace, post)
    events = _trajectory_events(task, agent_result, post, patch)
    final_text = (output / "agent" / "final.md").read_text(encoding="utf-8")
    for event in events:
        if event["kind"] == "final":
            event["content"] = final_text
    with (output / "trajectory.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    if agent_result["status"] == "timeout":
        status = "timeout"
    elif agent_result["status"] != "completed" or not post_ok or unexpected or not machine_ok:
        status = "failed"
    elif semantic_pending:
        status = "completed_pending_judgment"
    else:
        status = "completed"
    agent_summary = {key: value for key, value in agent_result.items() if key != "visible_events"}
    summary = {
        "schema_version": "growing-bench-run-2.0", "task_id": task["task_id"],
        "kind": task["kind"], "title": task.get("title", task["task_id"]),
        "status": status, "agent": agent, "model": model,
        "intervention": str(intervention) if intervention else None,
        "baseline_expectation_met": baseline_ok, "post_checks_passed": post_ok,
        "allowed_paths_ok": not unexpected, "unexpected_changed_paths": unexpected,
        "machine_completion_passed": machine_ok,
        "semantic_completion_pending": semantic_pending,
        "criterion_results": criterion_results,
        "elapsed_seconds": time.perf_counter() - total_started,
        "changes": changes, "agent_result": agent_summary,
        "isolation": isolation_profile(agent, isolation),
        "artifacts": {
            "trajectory": "trajectory.jsonl", "agent_events": "agent/events.jsonl",
            "final": "agent/final.md", "raw_stdout": "agent/stdout.log",
            "raw_stderr": "agent/stderr.log", "diff": "changes.diff",
            "workspace": "workspace", "before_checks": "checks.before.json",
            "after_checks": "checks.after.json",
        },
    }
    _write_json(output / "summary.json", summary)
    return summary
