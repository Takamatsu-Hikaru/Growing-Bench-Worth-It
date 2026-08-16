from __future__ import annotations

import json
from pathlib import Path

from growing_bench.execution import run_task


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    task = ROOT / "tracks" / "workspace-community-2026-08" / "tasks" / "cli-slug-helper" / "task.json"
    output = ROOT / "runs" / "living-cli-slug-helper-v1"
    template = json.dumps([
        "python", str(ROOT / "tools" / "codex_proposal_agent.py"),
        "--prompt-file", "{prompt_file}",
        "--raw-output", str(output / "child-codex.raw.log"),
        "--model", "gpt-5.6-sol", "--allowed", "src/commands.py",
    ])
    result = run_task(task, output, model="gpt-5.6-sol", reasoning="high", timeout=900, agent="command", command_template=template)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("post_checks_passed") and result.get("allowed_paths_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
