from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from workspace_eval import EVAL_ROOT, extract_object, prompt, validate_response, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--adjudicate", action="store_true")
    args = parser.parse_args()
    executable = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    if not executable:
        raise SystemExit("codex CLI is unavailable")
    command = [
        executable, "exec", "--ignore-rules", "--ephemeral", "--disable", "plugins", "--disable", "remote_plugin", "--disable", "plugin_sharing",
        "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json",
        "--cd", str(EVAL_ROOT), "--model", args.model, "-",
    ]
    with tempfile.TemporaryDirectory(prefix="growing-bench-judge-home-") as temp_name:
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
            "CODEX_HOME": str(codex_home), "HOME": str(profile), "USERPROFILE": str(profile),
            "HOMEDRIVE": profile_drive, "HOMEPATH": profile_tail,
            "APPDATA": str(isolation_root / "appdata"), "LOCALAPPDATA": str(isolation_root / "localappdata"),
            "XDG_CONFIG_HOME": str(isolation_root / "xdg-config"),
            "XDG_DATA_HOME": str(isolation_root / "xdg-data"),
            "XDG_CACHE_HOME": str(isolation_root / "xdg-cache"),
        })
        completed = subprocess.run(
            command, input=prompt(args.adjudicate), text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=1200, check=False, env=child_env,
        )
    (EVAL_ROOT / f"{args.label}.raw.log").write_text(
        completed.stdout + "\n--- STDERR ---\n" + completed.stderr,
        encoding="utf-8", newline="\n",
    )
    messages = []
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(str(item.get("text") or ""))
    if completed.returncode != 0 or not messages:
        raise SystemExit(f"judge {args.label} failed; inspect raw log")
    value = extract_object(messages[-1])
    validate_response(value)
    write_json(EVAL_ROOT / f"{args.label}.json", value)
    print(json.dumps({"label": args.label, "model": args.model, "item_count": len(value["items"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
