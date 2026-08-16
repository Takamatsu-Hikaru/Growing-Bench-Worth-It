from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def allowed(relative: str, roots: list[str]) -> bool:
    normalized = relative.replace("\\", "/").strip("/")
    return any(normalized == root.strip("/") or normalized.startswith(root.strip("/") + "/") for root in roots)


def extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1])
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("agent did not return a JSON edit request")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict) or not isinstance(parsed.get("changes"), list):
        raise ValueError("agent JSON requires a changes array")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--allowed", action="append", required=True)
    args = parser.parse_args()
    executable = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    if not executable:
        raise SystemExit("codex CLI is unavailable")
    instruction = args.prompt_file.read_text(encoding="utf-8") + """

The host exposes this workspace read-only to your inspection tools. Inspect the
actual files and run any read-only diagnostic or focused baseline check you
need. Do not attempt a file-write tool call. Your final response must be one
JSON object and nothing else:

{"changes":[{"path":"relative/allowed/path","content":"complete new UTF-8 file contents"}],"final":"short summary and checks considered"}

Return complete file contents, not a diff. Change only files necessary for the
task. The host will validate allowed paths, apply the edits, run the declared
checks, and record the resulting diff.
"""
    command = [
        executable, "exec", "--ignore-rules", "--ephemeral", "--disable", "plugins", "--disable", "remote_plugin", "--disable", "plugin_sharing",
        "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
        "--json", "--cd", str(Path.cwd()), "--model", args.model, "-",
    ]
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="growing-bench-codex-home-") as temp_name:
        isolation_root = Path(temp_name)
        codex_home = isolation_root / "codex-home"
        profile = isolation_root / "profile"
        codex_home.mkdir()
        profile.mkdir()
        user_home = Path.home()
        source_auth = user_home / ".codex" / "auth.json"
        if source_auth.is_file():
            shutil.copyfile(source_auth, codex_home / "auth.json")
        skill_files: list[Path] = []
        for skill_root in (
            user_home / ".agents" / "skills",
            user_home / ".codex" / "skills",
            user_home / ".codex" / "plugins" / "cache",
        ):
            if skill_root.is_dir():
                skill_files.extend(skill_root.rglob("SKILL.md"))
        config_lines = []
        for skill_file in sorted(set(path.resolve() for path in skill_files)):
            config_lines.extend((
                "[[skills.config]]",
                f"path = {json.dumps(str(skill_file))}",
                "enabled = false",
                "",
            ))
        (codex_home / "config.toml").write_text("\n".join(config_lines), encoding="utf-8", newline="\n")
        child_env = dict(os.environ)
        profile_drive, profile_tail = os.path.splitdrive(str(profile))
        child_env.update({
            "CODEX_HOME": str(codex_home),
            "HOME": str(profile),
            "USERPROFILE": str(profile),
            "HOMEDRIVE": profile_drive,
            "HOMEPATH": profile_tail,
            "APPDATA": str(isolation_root / "appdata"),
            "LOCALAPPDATA": str(isolation_root / "localappdata"),
            "XDG_CONFIG_HOME": str(isolation_root / "xdg-config"),
            "XDG_DATA_HOME": str(isolation_root / "xdg-data"),
            "XDG_CACHE_HOME": str(isolation_root / "xdg-cache"),
        })
        process = subprocess.run(
            command, input=instruction, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=900, check=False, env=child_env,
        )
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(
        process.stdout + "\n--- STDERR ---\n" + process.stderr,
        encoding="utf-8", newline="\n",
    )
    messages: list[str] = []
    child_events: list[dict[str, Any]] = []
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = item.get("type")
        if event_type == "item.completed" and item_type == "agent_message":
            messages.append(str(item.get("text") or ""))
        if event_type == "item.completed" and item_type == "command_execution":
            command_text = str(item.get("command") or "")
            folded = command_text.casefold()
            kind = "test_result" if any(token in folded for token in ("pytest", "unittest", "checks.check", "pdflatex")) else "command_result"
            child_events.append({
                "kind": kind, "timestamp": now(), "duration_ms": None,
                "tool": "codex-read-only-shell", "target": None,
                "status": "success" if item.get("exit_code") == 0 else "failure",
                "content": command_text, "visible_output": item.get("aggregated_output"),
            })
        elif event_type == "item.completed" and item_type == "agent_message" and len(messages) > 1:
            child_events.append({
                "kind": "assistant_message", "timestamp": now(), "duration_ms": None,
                "tool": None, "target": None, "status": "success", "content": messages[-1],
                "visible_output": None,
            })
    if process.returncode != 0 or not messages:
        print(json.dumps({"final": "Codex proposal failed", "events": child_events}, ensure_ascii=False))
        return 2
    try:
        proposal = extract_json(messages[-1])
        writes = []
        for change in proposal["changes"]:
            if not isinstance(change, dict) or not isinstance(change.get("path"), str) or not isinstance(change.get("content"), str):
                raise ValueError("each change requires string path and content")
            relative = change["path"].replace("\\", "/").strip("/")
            if ".." in Path(relative).parts or not allowed(relative, args.allowed):
                raise ValueError(f"change outside allowed paths: {relative}")
            target = (Path.cwd() / relative).resolve()
            if not target.is_relative_to(Path.cwd().resolve()):
                raise ValueError(f"change escapes workspace: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change["content"], encoding="utf-8", newline="\n")
            writes.append(relative)
            child_events.append({
                "kind": "file_write", "timestamp": now(), "duration_ms": None,
                "tool": "host-edit-executor", "target": relative, "status": "success",
                "content": f"Applied model-proposed complete contents to {relative}", "visible_output": None,
            })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        child_events.append({
            "kind": "artifact", "timestamp": now(), "duration_ms": None,
            "tool": "host-edit-executor", "target": None, "status": "failure",
            "content": str(exc), "visible_output": None,
        })
        print(json.dumps({"final": f"Proposal rejected: {exc}", "events": child_events}, ensure_ascii=False))
        return 2
    child_events.append({
        "kind": "artifact", "timestamp": now(), "duration_ms": (time.perf_counter() - started) * 1000,
        "tool": "codex-proposal-agent", "target": None, "status": "success",
        "content": f"Applied {len(writes)} allowed model-proposed file(s); temporary Codex home with {len(skill_files)} discovered user/plugin skills explicitly disabled", "visible_output": None,
    })
    print(json.dumps({"final": str(proposal.get("final") or "Completed requested workspace edit."), "events": child_events}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
