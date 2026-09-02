from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .task_contract import ORACLE_POLICIES, load_task, resolve_fixture


def _safe_package_path(task_dir: Path, relative: str, label: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError(f"{label} must be a relative path without parent traversal")
    resolved = (task_dir / raw).resolve()
    if not resolved.is_relative_to(task_dir.resolve()):
        raise ValueError(f"{label} escapes the task package")
    return resolved


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _visible_text(task: dict[str, Any], fixture: Path) -> list[tuple[str, str]]:
    public_task = {key: value for key, value in task.items() if key != "evaluation_visibility"}
    rows = [("task.json", json.dumps(public_task, ensure_ascii=False, sort_keys=True))]
    for path in sorted(fixture.rglob("*")):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        rows.append((
            f"fixture/{path.relative_to(fixture).as_posix()}",
            data.decode("utf-8", errors="replace"),
        ))
    return rows


def validate_custom_self_test_visibility(task_path: Path) -> dict[str, Any]:
    """Fail closed when a custom self-test cannot establish oracle separation."""

    task_path = task_path.resolve()
    task = load_task(task_path)
    visibility = task.get("evaluation_visibility")
    if not isinstance(visibility, dict) or visibility.get("oracle_policy") not in ORACLE_POLICIES:
        raise ValueError(
            "custom self-test tasks require evaluation_visibility.oracle_policy "
            "('not_applicable' or 'host_only'); see docs/SELF_TEST.md"
        )
    has_semantic_criterion = any(
        isinstance(row, dict) and row.get("kind") == "semantic"
        for row in task.get("completion_criteria", [])
    )
    policy = visibility["oracle_policy"]
    if policy == "not_applicable":
        if has_semantic_criterion or visibility.get("hidden"):
            raise ValueError(
                "oracle_policy 'not_applicable' cannot be used with semantic criteria "
                "or hidden evaluation targets"
            )
        return {
            "task_id": task["task_id"],
            "status": "admitted",
            "oracle_policy": policy,
            "evaluation_integrity": "public_checks_only",
            "oracle_overlap_checked": False,
        }

    if not has_semantic_criterion or not visibility.get("hidden"):
        raise ValueError(
            "oracle_policy 'host_only' requires at least one semantic completion criterion "
            "and one hidden target"
        )
    hidden_spec_value = visibility.get("hidden_spec")
    if not isinstance(hidden_spec_value, str) or not hidden_spec_value:
        raise ValueError("host_only custom tasks require evaluation_visibility.hidden_spec")
    task_dir = task_path.parent
    hidden_spec = _safe_package_path(
        task_dir, hidden_spec_value, "evaluation_visibility.hidden_spec"
    )
    reference_root = (task_dir / "reference").resolve()
    if not hidden_spec.is_relative_to(reference_root) or not hidden_spec.is_file():
        raise ValueError(
            "the hidden spec must be an existing file under reference/, "
            "outside the Agent fixture"
        )
    fixture = resolve_fixture(task_path, task)
    spec = json.loads(hidden_spec.read_text(encoding="utf-8"))
    oracle_values = spec.get("oracle_values") if isinstance(spec, dict) else None
    if not isinstance(oracle_values, list) or not oracle_values or not all(
        isinstance(item, str) and len(_normalized(item)) >= 4 for item in oracle_values
    ):
        raise ValueError("the hidden spec requires a nonempty oracle_values string array")
    visible = [(source, _normalized(text)) for source, text in _visible_text(task, fixture)]
    leaks = sorted({
        source
        for value in oracle_values
        for source, text in visible
        if _normalized(value) in text
    })
    if leaks:
        raise ValueError(f"semantic oracle is Agent-visible in: {', '.join(leaks)}")
    return {
        "task_id": task["task_id"],
        "status": "admitted",
        "oracle_policy": policy,
        "evaluation_integrity": "host_only_oracle",
        "hidden_spec": hidden_spec.relative_to(task_dir).as_posix(),
        "oracle_overlap_checked": True,
        "visible_files_checked": len(visible),
    }
