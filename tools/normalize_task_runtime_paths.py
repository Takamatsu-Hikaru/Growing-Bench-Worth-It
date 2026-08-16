from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tracks" / "workspace-v0.2" / "tasks"


def main() -> int:
    changed = 0
    for task_path in sorted(TASKS.glob("*/task.json")):
        task = json.loads(task_path.read_text(encoding="utf-8"))
        values = list(task.get("ignore_paths", []))
        if task["kind"] == "code":
            for path in ("src/__pycache__", "checks/__pycache__"):
                if path not in values:
                    values.append(path)
        task["ignore_paths"] = values
        task_path.write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        changed += 1
    print(f"normalized runtime ignore paths for {changed} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
