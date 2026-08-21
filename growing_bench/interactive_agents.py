from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .agents import (
    BUILTIN_AGENTS,
    _claude_final,
    _command_final,
    _executable,
    _openclaw_final,
    _run_captured,
    probe_agent,
)
from .quality import trajectory_completeness
from .trajectory import normalize_agent_events, utc_now


REPLAY_POLICY_ADAPTERS = {"openclaw", "command"}


def _codex_thread_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("type") == "thread.started" and isinstance(value.get("thread_id"), str):
            return value["thread_id"]
    return None


def _command(
    agent: str,
    workspace: Path,
    prompt_file: Path,
    final_file: Path,
    session_dir: Path,
    session_id: str | None,
    turn_index: int,
    model: str | None,
    reasoning: str,
    timeout: float,
    command_template: str | None,
) -> tuple[list[str], str | None, str | None, str]:
    executable = _executable(agent) if agent != "command" else None
    if agent != "command" and executable is None:
        raise FileNotFoundError(f"{agent} CLI is not installed or not on PATH")
    if agent == "codex":
        common = [
            "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
            "--json", "--output-last-message", str(final_file),
            "--config", f'model_reasoning_effort="{reasoning}"',
        ]
        if model:
            common.extend(["--model", model])
        if session_id:
            return [executable, "exec", "resume", *common, session_id, "-"], prompt_file.read_text(encoding="utf-8"), session_id, "native"
        return [
            executable, "exec", *common, "--sandbox", "workspace-write",
            "--cd", str(workspace), "-",
        ], prompt_file.read_text(encoding="utf-8"), None, "native"
    if agent == "claude-code":
        current_id = session_id or str(uuid.uuid4())
        command = [
            executable, "--bare", "--safe-mode", "--print",
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits", "--effort", reasoning,
            "--add-dir", str(workspace),
        ]
        if model:
            command.extend(["--model", model])
        command.extend(["--resume", current_id] if session_id else ["--session-id", current_id])
        command.append(prompt_file.read_text(encoding="utf-8"))
        return command, None, current_id, "native"
    if agent == "openclaw":
        command = [
            executable, "agent", "exec", "--message-file", str(prompt_file),
            "--cwd", str(workspace), "--json", "--timeout", str(max(1, int(timeout))),
            "--thinking", reasoning,
        ]
        if model:
            command.extend(["--model", model])
        return command, None, session_id or f"openclaw-replay-{uuid.uuid4()}", "transcript_replay"
    if not command_template:
        raise ValueError("command adapter requires --command-template as a JSON string array")
    raw = json.loads(command_template)
    if not isinstance(raw, list) or not raw or not all(isinstance(part, str) and part for part in raw):
        raise ValueError("command template must be a nonempty JSON string array")
    current_id = session_id or f"command-{uuid.uuid4()}"
    replacements = {
        "{workspace}": str(workspace), "{prompt_file}": str(prompt_file),
        "{final_file}": str(final_file), "{session_dir}": str(session_dir),
        "{session_id}": current_id, "{turn_index}": str(turn_index),
        "{model}": model or "", "{reasoning}": reasoning,
    }
    return [replacements.get(part, part) for part in raw], None, current_id, "adapter_managed"


def run_agent_turn(
    agent: str,
    prompt: str,
    workspace: Path,
    artifacts: Path,
    session_dir: Path,
    *,
    session_id: str | None = None,
    turn_index: int = 1,
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    intervention: Path | None = None,
    command_template: str | None = None,
) -> dict[str, Any]:
    """Run one real workspace turn while preserving conversation state."""

    if agent not in BUILTIN_AGENTS:
        raise ValueError(f"unknown agent {agent!r}; choose from {BUILTIN_AGENTS}")
    artifacts.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)
    intervention_applied = intervention is not None and (
        turn_index == 1 or agent in REPLAY_POLICY_ADAPTERS
    )
    if intervention_applied:
        prompt = (
            f"{prompt}\n\n## Session intervention policy\n\n"
            f"{intervention.read_text(encoding='utf-8')}"
        )
    prompt_file, final_file = artifacts / "prompt.md", artifacts / "final.md"
    prompt_file.write_text(prompt, encoding="utf-8", newline="\n")
    command, stdin, declared_id, persistence = _command(
        agent, workspace, prompt_file, final_file, session_dir, session_id,
        turn_index, model, reasoning, timeout, command_template,
    )
    try:
        returncode, stdout, stderr, status, elapsed, started_at, finished_at, records = _run_captured(
            command, stdin, workspace, timeout
        )
    except OSError as exc:
        returncode, stdout, stderr, status = None, "", str(exc), "failed"
        elapsed, started_at, finished_at, records = 0.0, utc_now(), utc_now(), []
    (artifacts / "stdout.log").write_text(stdout, encoding="utf-8", newline="\n")
    (artifacts / "stderr.log").write_text(stderr, encoding="utf-8", newline="\n")
    if final_file.is_file():
        final, usage = final_file.read_text(encoding="utf-8"), None
    elif agent == "claude-code":
        final, usage = _claude_final(stdout)
    elif agent == "openclaw":
        final, usage = _openclaw_final(stdout)
    else:
        final, usage = _command_final(stdout)
    final_file.write_text(final, encoding="utf-8", newline="\n")
    visible_events = normalize_agent_events(agent, records)
    with (artifacts / "events.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for event in visible_events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    resolved_id = session_id or declared_id
    if agent == "codex" and not session_id:
        resolved_id = _codex_thread_id(stdout)
    if status == "completed" and not resolved_id:
        status = "failed"
        stderr = (stderr + "\nInteractive adapter did not expose a session identifier.").strip()
        (artifacts / "stderr.log").write_text(stderr, encoding="utf-8", newline="\n")
    result = {
        "schema_version": "growing-bench-agent-turn-1.0",
        "agent": agent, "agent_version": probe_agent(agent).get("version"),
        "model": model, "reasoning": reasoning, "status": status,
        "returncode": returncode, "elapsed_seconds": elapsed,
        "started_at": started_at, "finished_at": finished_at,
        "turn_index": turn_index, "session_id": resolved_id,
        "session_persistence": persistence, "usage": usage,
        "intervention_policy_applied": intervention_applied,
        "visible_event_count": len(visible_events),
        "trajectory_completeness": trajectory_completeness(agent, visible_events),
        "visible_events": visible_events, "final": final,
        "artifacts": {
            "prompt": "prompt.md", "final": "final.md", "stdout": "stdout.log",
            "stderr": "stderr.log", "events": "events.jsonl",
        },
    }
    (artifacts / "turn.json").write_text(
        json.dumps({key: value for key, value in result.items() if key != "visible_events"}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return result
