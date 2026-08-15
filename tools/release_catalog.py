#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, values: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def release_publication(value: dict[str, Any]) -> None:
    value["permission_asserted_by_catalog"] = True
    value["release_eligible"] = True
    value["upstream_status"] = "released-project-authored-adaptation"


def main() -> int:
    task_path = ROOT / "data" / "tasks" / "tasks.jsonl"
    provenance_path = ROOT / "data" / "tasks" / "provenance.jsonl"
    tasks = rows(task_path)
    provenance = rows(provenance_path)
    if len(tasks) != 34 or len(provenance) != 34:
        raise ValueError("v0.1 release requires exactly 34 tasks and 34 provenance rows")
    for task in tasks:
        task["release_status"] = "released"
        task["release_version"] = "0.1.0"
        task.setdefault("provenance", {})["publication_status"] = "released"
        release_publication(task.setdefault("publication", {}))
    for row in provenance:
        row["release_status"] = "released"
        row["release_version"] = "0.1.0"
        release_publication(row.setdefault("publication", {}))
    if {row["task_id"] for row in tasks} != {row["task_id"] for row in provenance}:
        raise ValueError("task and provenance IDs differ")
    write_rows(task_path, tasks)
    write_rows(provenance_path, provenance)
    print("released 34 tasks as v0.1.0; stable staging-prefixed IDs retained for result compatibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
