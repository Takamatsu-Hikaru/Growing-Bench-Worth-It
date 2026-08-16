from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def extract(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("curator did not return a JSON object")
    return json.loads(text[start : end + 1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = args.case.resolve()
    prompt = f"""You are the independent AI curator for a living agent benchmark. Review the Markdown case below and its declared portable workspace package. Do not solve the task and do not infer model/intervention results. Decide whether the case can enter staging. Check exactly: information sufficiency; observable completion criteria; provenance; publication permission; duplicate risk based only on the case; possible positive/negative pairing; and real executability. Return one JSON object and no prose:
{{
  "curator_model": "{args.model}",
  "decision": "admit|revise|reject",
  "decisions": {{
    "information_sufficient": true,
    "criteria_observable": true,
    "provenance_acceptable": true,
    "publication_allowed": true,
    "duplicate_risk": false,
    "pairing_possible": true,
    "executable": true
  }},
  "rationale": "specific concise rationale",
  "unresolved": []
}}

CASE:
{case.read_text(encoding='utf-8')}

VISIBLE FILE INVENTORY:
{chr(10).join(str(p.relative_to(case.parent)) for p in sorted(case.parent.rglob('*')) if p.is_file())}
"""
    executable = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    if not executable:
        raise SystemExit("codex CLI unavailable")
    command = [executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json", "--cd", str(case.parent), "--model", args.model, "-"]
    done = subprocess.run(command, input=prompt, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=1200, check=False)
    raw = args.output.with_suffix(".raw.log")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(done.stdout + "\n--- STDERR ---\n" + done.stderr, encoding="utf-8", newline="\n")
    messages = []
    for line in done.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(str(item.get("text") or ""))
    if done.returncode or not messages:
        raise SystemExit(f"curator failed; inspect {raw}")
    value = extract(messages[-1])
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"decision": value.get("decision"), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
