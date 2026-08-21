from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .agents import run_agent
from .execution import _baseline_valid, _check_event_kind, _diff, _file_map, _run_checks, _under
from .interactive_agents import run_agent_turn
from .paths import REPOSITORY_ROOT
from .task_contract import evaluate_completion, load_task, resolve_fixture
from .trajectory import utc_now


SCENARIO_SCHEMA_VERSION = "growing-bench-interactive-scenario-1.0"
RUN_SCHEMA_VERSION = "growing-bench-interactive-run-1.0"
TURN_ROLES = {"initial", "correction", "followup", "takeover"}
USER_MODES = {"scripted", "simulated"}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def validate_scenario(value: dict[str, Any]) -> None:
    required = {"schema_version", "scenario_id", "base_task_id", "user_profile", "turns"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError(f"interactive scenario requires {sorted(required)}")
    if value["schema_version"] != SCENARIO_SCHEMA_VERSION:
        raise ValueError("interactive scenario schema_version is invalid")
    for field in ("scenario_id", "base_task_id"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError(f"interactive scenario {field} is required")
    if not isinstance(value["user_profile"], dict):
        raise ValueError("interactive scenario user_profile must be an object")
    turns = value["turns"]
    if not isinstance(turns, list) or len(turns) < 2:
        raise ValueError("interactive scenario requires at least two user turns")
    seen: set[str] = set()
    initial_count = 0
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError(f"turns[{index}] must be an object")
        move_id = turn.get("move_id")
        if not isinstance(move_id, str) or not move_id or move_id in seen:
            raise ValueError(f"turns[{index}] requires a unique move_id")
        seen.add(move_id)
        role = turn.get("role")
        if role not in TURN_ROLES:
            raise ValueError(f"turns[{index}].role must be one of {sorted(TURN_ROLES)}")
        initial_count += int(role == "initial")
        message = turn.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"turns[{index}].message is required")
        for field in ("activates", "retires", "targets"):
            rows = turn.get(field, [])
            if not isinstance(rows, list) or not all(isinstance(item, str) and item for item in rows):
                raise ValueError(f"turns[{index}].{field} must be a string array")
    if initial_count != 1 or turns[0]["role"] != "initial":
        raise ValueError("interactive scenario must begin with exactly one initial turn")


def load_scenario(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_scenario(value)
    return value


def resolve_task(task_id: str) -> Path:
    repository = REPOSITORY_ROOT / "tracks" / "workspace-v0.2" / "tasks" / task_id / "task.json"
    if repository.is_file():
        return repository
    packaged = Path(__file__).resolve().parent / "resources" / "suites" / "workspace-v0.2" / task_id / "task.json"
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(f"interactive base task is unavailable: {task_id}")


def _simulator_prompt(
    scenario: dict[str, Any], turn: dict[str, Any], transcript: list[dict[str, str]],
) -> str:
    return f"""You are the user in a controlled Agent evaluation. Express the supplied move naturally and concisely.

You may use only the supplied facts. Do not add requirements, facts, judgments, feelings, or workspace claims. Do not score the tested Agent. Return one JSON object with exactly move_id and message.

USER PROFILE:
{json.dumps(scenario['user_profile'], ensure_ascii=False, sort_keys=True)}

REQUIRED MOVE:
{json.dumps(turn, ensure_ascii=False, sort_keys=True)}

VISIBLE CONVERSATION:
{json.dumps(transcript, ensure_ascii=False, sort_keys=True)}
"""


def _extract_simulated_message(text: str, move_id: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.lstrip().startswith("json"):
            value = value.lstrip()[4:].lstrip()
    try:
        row = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("user simulator did not return JSON") from exc
    if not isinstance(row, dict) or set(row) != {"move_id", "message"}:
        raise ValueError("user simulator must return exactly move_id and message")
    if row["move_id"] != move_id or not isinstance(row["message"], str) or not row["message"].strip():
        raise ValueError("user simulator returned an invalid move")
    return row["message"].strip()


def _user_message(
    scenario: dict[str, Any], turn: dict[str, Any], task: dict[str, Any],
    transcript: list[dict[str, str]], output: Path, user_mode: str,
    user_agent: str, user_model: str | None, user_reasoning: str,
    timeout: float, user_command_template: str | None,
) -> str:
    if turn["message"] == "$TASK_PROMPT":
        return task["prompt"]
    if user_mode == "scripted":
        return turn["message"].strip()
    with tempfile.TemporaryDirectory(prefix="growing-user-sim-") as name:
        workspace = Path(name)
        result = run_agent(
            user_agent, _simulator_prompt(scenario, turn, transcript), workspace,
            output, model=user_model, reasoning=user_reasoning, timeout=timeout,
            command_template=user_command_template,
        )
    if result["status"] != "completed":
        raise ValueError(f"user simulator failed for move {turn['move_id']}")
    final = (output / "final.md").read_text(encoding="utf-8")
    return _extract_simulated_message(final, turn["move_id"])


def _agent_prompt(message: str, transcript: list[dict[str, str]], persistence: str | None) -> str:
    if persistence not in {"transcript_replay", "adapter_managed"} or not transcript:
        return message
    history = "\n\n".join(f"{row['role'].upper()}: {row['content']}" for row in transcript)
    return f"Continue the same workspace task from this visible conversation.\n\n{history}\n\nUSER: {message}"


def run_interactive_scenario(
    scenario_path: Path,
    output: Path,
    *,
    agent: str = "codex",
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    intervention: Path | None = None,
    command_template: str | None = None,
    user_mode: str = "scripted",
    user_agent: str = "codex",
    user_model: str | None = None,
    user_reasoning: str = "medium",
    user_command_template: str | None = None,
) -> dict[str, Any]:
    """Execute a multi-turn scenario against one persistent workspace Agent."""

    if user_mode not in USER_MODES:
        raise ValueError(f"unknown user mode {user_mode!r}; choose from {sorted(USER_MODES)}")
    scenario_path, output = scenario_path.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    scenario = load_scenario(scenario_path)
    task_path = resolve_task(scenario["base_task_id"])
    task = load_task(task_path)
    fixture = resolve_fixture(task_path, task)
    output.mkdir(parents=True)
    before, workspace = output / "before", output / "workspace"
    shutil.copytree(fixture, before)
    shutil.copytree(fixture, workspace)
    _write_json(output / "scenario.json", scenario)
    _write_json(output / "task.json", task)
    baseline = _run_checks(task, before)
    _write_json(output / "checks.before.json", baseline)
    if not _baseline_valid(task, baseline):
        summary = {
            "schema_version": RUN_SCHEMA_VERSION, "scenario_id": scenario["scenario_id"],
            "task_id": task["task_id"], "status": "baseline_invalid", "turn_count": 0,
        }
        _write_json(output / "summary.json", summary)
        return summary

    started = time.perf_counter()
    initial_files = _file_map(before, task["ignore_paths"])
    previous_files = dict(initial_files)
    transcript: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    controller: list[dict[str, Any]] = []
    session_id: str | None = None
    persistence: str | None = None
    turn_results: list[dict[str, Any]] = []
    active: set[str] = set(scenario.get("initial_active", []))
    retired: set[str] = set()
    failed = False

    for index, turn in enumerate(scenario["turns"], start=1):
        message = _user_message(
            scenario, turn, task, transcript, output / "user-simulator" / f"turn-{index:02d}",
            user_mode, user_agent, user_model, user_reasoning, timeout, user_command_template,
        )
        active.update(turn.get("activates", []))
        for item in turn.get("retires", []):
            active.discard(item)
            retired.add(item)
        user_event_id = f"{scenario['scenario_id']}::turn-{index:02d}::user"
        events.append({
            "event_id": user_event_id, "kind": "user_message", "turn_index": index,
            "timestamp": utc_now(), "duration_ms": None, "tool": None, "target": None,
            "status": "success", "content": message, "visible_output": None,
            "usage": None, "source_adapter": "interactive-controller",
            "source_event_type": turn["role"], "move_id": turn["move_id"],
        })
        controller.append({
            "turn_index": index, "move_id": turn["move_id"], "role": turn["role"],
            "targets": turn.get("targets", []), "active_after": sorted(active),
            "retired_after": sorted(retired), "message": message,
        })
        agent_prompt = _agent_prompt(message, transcript, persistence)
        result = run_agent_turn(
            agent, agent_prompt, workspace, output / "agent" / f"turn-{index:02d}",
            output / "agent" / "session", session_id=session_id, turn_index=index,
            model=model, reasoning=reasoning, timeout=timeout,
            intervention=intervention, command_template=command_template,
        )
        session_id = result.get("session_id")
        persistence = result.get("session_persistence")
        for event_index, raw in enumerate(result.get("visible_events", []), start=1):
            event = dict(raw)
            event["event_id"] = f"{scenario['scenario_id']}::turn-{index:02d}::agent-{event_index:04d}"
            event["turn_index"] = index
            events.append(event)
        final = result.get("final", "")
        duplicate_final = any(
            event.get("turn_index") == index and event.get("kind") == "assistant_message"
            and str(event.get("content") or "").strip() == final.strip()
            for event in events
        )
        if not duplicate_final:
            events.append({
                "event_id": f"{scenario['scenario_id']}::turn-{index:02d}::assistant",
                "kind": "assistant_message", "turn_index": index,
                "timestamp": result.get("finished_at") or utc_now(), "duration_ms": None,
                "tool": None, "target": None,
                "status": "success" if result["status"] == "completed" else "failure",
                "content": final, "visible_output": None, "usage": result.get("usage"),
                "source_adapter": agent, "source_event_type": "turn_final",
            })
        current_files = _file_map(workspace, task["ignore_paths"])
        changes, patch = _diff(previous_files, current_files)
        (output / "turn-diffs").mkdir(exist_ok=True)
        (output / "turn-diffs" / f"turn-{index:02d}.diff").write_text(patch, encoding="utf-8", newline="\n")
        if patch:
            events.append({
                "event_id": f"{scenario['scenario_id']}::turn-{index:02d}::diff",
                "kind": "diff", "turn_index": index, "timestamp": utc_now(),
                "duration_ms": None, "tool": "runner-diff", "target": f"turn-diffs/turn-{index:02d}.diff",
                "status": "success", "content": patch, "visible_output": None,
                "usage": None, "source_adapter": "interactive-runner",
                "source_event_type": "turn_workspace_diff",
            })
        previous_files = current_files
        transcript.extend([{"role": "user", "content": message}, {"role": "assistant", "content": final}])
        turn_results.append({
            "turn_index": index, "move_id": turn["move_id"], "role": turn["role"],
            "status": result["status"], "elapsed_seconds": result["elapsed_seconds"],
            "session_persistence": persistence, "changes": changes,
            "trajectory_completeness": result["trajectory_completeness"],
        })
        if result["status"] != "completed":
            failed = True
            break

    post = _run_checks(task, workspace)
    _write_json(output / "checks.after.json", post)
    final_changes, final_patch = _diff(initial_files, _file_map(workspace, task["ignore_paths"]))
    _write_json(output / "changes.json", final_changes)
    (output / "changes.diff").write_text(final_patch, encoding="utf-8", newline="\n")
    for check_index, row in enumerate(post, start=1):
        events.append({
            "event_id": f"{scenario['scenario_id']}::post-check::{check_index:02d}",
            "kind": _check_event_kind(row["command"]), "turn_index": len(turn_results) + 1,
            "timestamp": row["finished_at"], "duration_ms": row["elapsed_seconds"] * 1000.0,
            "tool": "runner-check", "target": row["name"],
            "status": "success" if row["passed"] else "failure",
            "content": " ".join(row["command"]),
            "visible_output": f"{row['stdout']}\n{row['stderr']}".strip(),
            "usage": None, "source_adapter": "interactive-runner", "source_event_type": "post_check",
        })
    _write_jsonl(output / "controller.jsonl", controller)
    _write_jsonl(output / "trajectory.jsonl", events)

    forbidden = task.get("forbidden_paths", [])
    unexpected = [
        path for path in final_changes["changed_paths"]
        if not _under(path, task["allowed_paths"]) or _under(path, forbidden)
    ]
    post_ok = bool(post) and all(row["passed"] for row in post)
    criterion_results, machine_ok, semantic_pending = evaluate_completion(task, workspace, post)
    if failed:
        status = "failed"
    elif not post_ok or unexpected or not machine_ok:
        status = "failed"
    elif semantic_pending:
        status = "completed_pending_judgment"
    else:
        status = "completed"
    summary = {
        "schema_version": RUN_SCHEMA_VERSION, "scenario_id": scenario["scenario_id"],
        "task_id": task["task_id"], "kind": task["kind"], "status": status,
        "agent": agent, "model": model, "user_mode": user_mode,
        "user_simulator": None if user_mode == "scripted" else {"agent": user_agent, "model": user_model},
        "turn_count": len(turn_results), "planned_turn_count": len(scenario["turns"]),
        "correction_count": sum(row["role"] == "correction" for row in controller),
        "takeover_occurred": any(row["role"] == "takeover" for row in controller),
        "session_persistence": persistence, "turns": turn_results,
        "baseline_expectation_met": True, "post_checks_passed": post_ok,
        "allowed_paths_ok": not unexpected, "unexpected_changed_paths": unexpected,
        "machine_completion_passed": machine_ok, "semantic_completion_pending": semantic_pending,
        "criterion_results": criterion_results, "changes": final_changes,
        "elapsed_seconds": time.perf_counter() - started,
        "artifacts": {
            "trajectory": "trajectory.jsonl", "controller": "controller.jsonl",
            "workspace": "workspace", "diff": "changes.diff",
            "before_checks": "checks.before.json", "after_checks": "checks.after.json",
        },
    }
    _write_json(output / "summary.json", summary)
    return summary
