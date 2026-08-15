from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


BUILTIN_AGENTS = ("codex", "claude-code", "openclaw", "command")


def _executable(name: str) -> str | None:
    candidates = {
        "codex": ("codex.cmd", "codex.exe", "codex"),
        "claude-code": ("claude.cmd", "claude.exe", "claude"),
        "openclaw": ("openclaw.cmd", "openclaw.exe", "openclaw"),
    }.get(name, ())
    return next((value for value in candidates if shutil.which(value)), None)


def probe_agent(name: str) -> dict[str, Any]:
    if name == "command":
        return {"agent": name, "available": True, "version": "user-supplied"}
    executable = _executable(name)
    if executable is None:
        return {"agent": name, "available": False, "version": None}
    try:
        value = subprocess.run(
            [executable, "--version"], text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=10, check=False,
        )
        version = (value.stdout or value.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        version = "unknown"
    return {"agent": name, "available": True, "version": version, "executable": executable}


def _claude_final(stdout: str) -> tuple[str, dict[str, Any] | None]:
    final, usage = "", None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            final = str(event.get("result") or final)
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else usage
        message = event.get("message")
        if isinstance(message, dict):
            parts = message.get("content")
            if isinstance(parts, list):
                texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("type") == "text"]
                if texts:
                    final = "\n".join(str(text) for text in texts)
    return final, usage


def _openclaw_final(stdout: str) -> tuple[str, dict[str, Any] | None]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), None
    return str(value.get("final") or ""), value.get("usage") if isinstance(value.get("usage"), dict) else None


def _command_final(stdout: str) -> tuple[str, dict[str, Any] | None]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), None
    if isinstance(value, dict):
        return str(value.get("final") or value.get("response") or stdout.strip()), value.get("usage")
    return stdout.strip(), None


def _build_command(
    agent: str,
    workspace: Path,
    prompt_file: Path,
    final_file: Path,
    model: str | None,
    reasoning: str,
    timeout: float,
    command_template: str | None,
) -> tuple[list[str], str | None]:
    executable = _executable(agent) if agent != "command" else None
    if agent != "command" and executable is None:
        raise FileNotFoundError(f"{agent} CLI is not installed or not on PATH")
    if agent == "codex":
        command = [
            executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never",
            "--json", "--cd", str(workspace), "--output-last-message", str(final_file),
            "--config", f'model_reasoning_effort="{reasoning}"',
        ]
        if model:
            command.extend(["--model", model])
        command.append("-")
        return command, prompt_file.read_text(encoding="utf-8")
    if agent == "claude-code":
        command = [
            executable, "--bare", "--print", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--permission-mode", "acceptEdits",
            "--effort", reasoning, "--add-dir", str(workspace),
        ]
        if model:
            command.extend(["--model", model])
        command.append(prompt_file.read_text(encoding="utf-8"))
        return command, None
    if agent == "openclaw":
        command = [
            executable, "agent", "exec", "--message-file", str(prompt_file),
            "--cwd", str(workspace), "--json", "--timeout", str(max(1, int(timeout))),
            "--thinking", reasoning,
        ]
        if model:
            command.extend(["--model", model])
        return command, None
    if not command_template:
        raise ValueError("command adapter requires --command-template as a JSON string array")
    raw = json.loads(command_template)
    if not isinstance(raw, list) or not raw or not all(isinstance(part, str) and part for part in raw):
        raise ValueError("command template must be a nonempty JSON string array")
    replacements = {
        "{workspace}": str(workspace), "{prompt_file}": str(prompt_file),
        "{final_file}": str(final_file), "{model}": model or "", "{reasoning}": reasoning,
    }
    return [replacements.get(part, part) for part in raw], None


def run_agent(
    agent: str,
    prompt: str,
    workspace: Path,
    artifacts: Path,
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    intervention: Path | None = None,
    command_template: str | None = None,
) -> dict[str, Any]:
    if agent not in BUILTIN_AGENTS:
        raise ValueError(f"unknown agent {agent!r}; choose from {BUILTIN_AGENTS}")
    artifacts.mkdir(parents=True, exist_ok=True)
    if intervention is not None:
        intervention_text = intervention.read_text(encoding="utf-8")
        prompt = f"{prompt}\n\n## Additional intervention\n\n{intervention_text}"
    prompt_file, final_file = artifacts / "prompt.md", artifacts / "final.md"
    prompt_file.write_text(prompt, encoding="utf-8", newline="\n")
    command, stdin = _build_command(
        agent, workspace, prompt_file, final_file, model, reasoning, timeout, command_template
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, input=stdin, cwd=workspace, env=os.environ.copy(), text=True,
            encoding="utf-8", errors="replace", capture_output=True,
            timeout=timeout, check=False,
        )
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        status = "completed" if returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        returncode, stdout, stderr, status = None, exc.stdout or "", exc.stderr or "", "timeout"
    elapsed = time.perf_counter() - started
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
    result = {
        "schema_version": "growing-bench-agent-run-1.0",
        "agent": agent, "agent_version": probe_agent(agent).get("version"),
        "model": model, "reasoning": reasoning, "status": status,
        "returncode": returncode, "elapsed_seconds": elapsed, "usage": usage,
        "artifacts": {"prompt": "prompt.md", "final": "final.md", "stdout": "stdout.log", "stderr": "stderr.log"},
    }
    (artifacts / "agent.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return result
