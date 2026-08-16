from __future__ import annotations

import json
from pathlib import Path

from build_workspace_track import TRACK, task_id, writing_specs


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    tasks_root = TRACK / "tasks"
    for task_path in sorted(tasks_root.glob("*/task.json")):
        task = json.loads(task_path.read_text(encoding="utf-8"))
        if task["kind"] == "code":
            check_package = task_path.parent / "fixture" / "checks" / "__init__.py"
            check_package.write_text("", encoding="utf-8")
            task["checks"][0]["command"] = ["python", "-m", "checks.check"]
            write_json(task_path, task)

    cache_stub = tasks_root / "workspace-v0.2--code-cache--bounded-cache-required" / "fixture" / "src" / "catalog.py"
    cache_stub.write_text(
        '_CACHE = {}\n\n\ndef load_catalog(path):\n    raise NotImplementedError("WORKSPACE_TASK_INCOMPLETE")\n',
        encoding="utf-8", newline="\n",
    )

    for spec in writing_specs():
        directory = tasks_root / task_id(spec)
        targets = spec.get("targets", ["sections/target.tex"])
        content = (
            "from pathlib import Path\n"
            f"targets={targets!r}\n"
            "text='\\n'.join(Path(path).read_text(encoding='utf-8') for path in targets)\n"
            f"required={spec['required']!r}\n"
            f"forbidden={spec['forbidden']!r}\n"
            "if 'WORKSPACE_TASK_INCOMPLETE' in text or any(value not in text for value in required) or any(value in text for value in forbidden):\n"
            "    print('WORKSPACE_TASK_INCOMPLETE')\n"
            "    raise SystemExit(1)\n"
            "print('ok')\n"
        )
        (directory / "fixture" / "checks" / "check_content.py").write_text(
            content, encoding="utf-8", newline="\n"
        )
    print("finalized 14 code and 12 writing task packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
