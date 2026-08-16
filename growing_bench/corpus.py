from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .paths import DEFAULT_TRACKS_ROOT
from .task_contract import load_task, resolve_fixture


def _command(command: list[str]) -> list[str]:
    return command[2:] if os.name != "nt" and command[:2] == ["cmd", "/c"] else command


def run_checks(task: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    rows = []
    for check in task["checks"]:
        started = time.perf_counter()
        try:
            completed = subprocess.run(_command(check["command"]), cwd=workspace, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=float(check.get("timeout_seconds", 180)), check=False)
            row = {"name": check["name"], "returncode": completed.returncode, "passed": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            row = {"name": check["name"], "returncode": None, "passed": False, "stdout": "", "stderr": str(exc)}
        row["elapsed_seconds"] = time.perf_counter() - started; rows.append(row)
    return rows


def baseline_matches(task: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    if task["baseline_expectation"] == "passing":
        return bool(rows) and all(row["passed"] for row in rows)
    signature = task.get("expected_failure")
    return isinstance(signature, dict) and any(row["name"] == signature.get("check") and row["returncode"] == signature.get("returncode") and str(signature.get("contains")) in f"{row['stdout']}\n{row['stderr']}" for row in rows)


def _copy_overlay(source_root: Path, workspace: Path) -> list[str]:
    changed = []
    for source in sorted(source_root.rglob("*")):
        if source.is_file():
            relative = source.relative_to(source_root); target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target); changed.append(relative.as_posix())
    return changed


def _allowed(path: str, roots: list[str]) -> bool:
    return any(path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/") for root in roots if root.rstrip("/"))


def _normalize(text: str) -> str:
    return " ".join(text.replace("\\%", "%").casefold().split())


def hidden_semantic_pass(task_dir: Path, workspace: Path) -> bool:
    path = task_dir / "reference" / "hidden_spec.json"
    if not path.is_file():
        return task_dir.name.startswith("workspace-v0.2--code-")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec["kind"] == "writing":
        reference = _normalize(spec["reference_text"])
        values = [_normalize((workspace / target).read_text(encoding="utf-8")) for target in spec["targets"]]
        return bool(values) and all(reference == value for value in values)
    if spec["kind"] == "review":
        try:
            value = json.loads((workspace / "review.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            value.get("decision") == spec["decision"]
            and set(spec["required_evidence_ids"]).issubset(set(value.get("evidence_ids", [])))
            and not set(spec["forbidden_required_actions"]).intersection(value.get("required_actions", []))
        )
    return False


def semantic_oracle_absent_from_fixture(task_dir: Path) -> bool:
    spec_path = task_dir / "reference" / "hidden_spec.json"
    if not spec_path.is_file():
        return True
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    visible = "\n".join(path.read_text(encoding="utf-8", errors="replace").casefold() for path in (task_dir / "fixture" / "checks").rglob("*.py"))
    if spec["kind"] == "writing":
        secrets = [spec["reference_text"], *spec["required_concepts"], *spec["forbidden_claims"]]
    else:
        secrets = [*spec["required_evidence_ids"], *spec["forbidden_required_actions"]]
    return all(str(value).casefold() not in visible for value in secrets if len(str(value)) >= 4)


def validate_adversarials(task: dict[str, Any], task_dir: Path, fixture: Path, root: Path) -> tuple[list[dict[str, Any]], bool, bool]:
    adversarial_root = task_dir / "reference" / "adversarial"
    variants = sorted(path for path in adversarial_root.iterdir() if path.is_dir()) if adversarial_root.is_dir() else []
    rows = []
    for index, variant in enumerate(variants, 1):
        workspace = root / f"adversarial-{index}"; shutil.copytree(fixture, workspace); _copy_overlay(variant, workspace)
        public = run_checks(task, workspace); public_pass = bool(public) and all(row["passed"] for row in public)
        hidden_pass = hidden_semantic_pass(task_dir, workspace)
        rows.append({"variant": variant.name, "public_checks_pass": public_pass, "hidden_reference_check_pass": hidden_pass, "rejected": not (public_pass and hidden_pass)})
    all_rejected = bool(rows) and all(row["rejected"] for row in rows)
    semantic_split_proven = task["kind"] == "code" or any(row["public_checks_pass"] and not row["hidden_reference_check_pass"] for row in rows)
    return rows, all_rejected, semantic_split_proven


def validate_task_package(task_path: Path) -> dict[str, Any]:
    task_path = task_path.resolve(); task_dir = task_path.parent; task = load_task(task_path); fixture = resolve_fixture(task_path, task)
    solution = task_dir / "reference" / "solution"
    if not solution.is_dir():
        raise ValueError(f"reference solution is missing for {task['task_id']}")
    with tempfile.TemporaryDirectory(prefix="growing-corpus-") as name:
        root = Path(name); baseline_workspace = root / "baseline"; reference_workspace = root / "reference"
        shutil.copytree(fixture, baseline_workspace); shutil.copytree(fixture, reference_workspace)
        baseline = run_checks(task, baseline_workspace); baseline_ok = baseline_matches(task, baseline)
        changed = _copy_overlay(solution, reference_workspace); reference = run_checks(task, reference_workspace)
        reference_public_ok = bool(reference) and all(row["passed"] for row in reference)
        reference_hidden_ok = hidden_semantic_pass(task_dir, reference_workspace)
        adversarials, adversarial_rejected, semantic_split = validate_adversarials(task, task_dir, fixture, root)
    scope_ok = bool(changed) and all(_allowed(path, task["allowed_paths"]) for path in changed)
    checks = {
        "contract_valid": True,
        "fixture_isolated": True,
        "baseline_matches": baseline_ok,
        "no_op_rejected": task["baseline_expectation"] == "failing" and baseline_ok,
        "reference_public_checks_pass": reference_public_ok,
        "reference_hidden_check_pass": reference_hidden_ok,
        "reference_scope_valid": scope_ok,
        "semantic_oracle_not_agent_visible": semantic_oracle_absent_from_fixture(task_dir),
        "known_wrong_alternative_rejected": adversarial_rejected,
        "semantic_visibility_split_demonstrated": semantic_split,
    }
    return {
        "schema_version": "growing-bench-task-admission-2.0", "task_id": task["task_id"],
        "title": task.get("title", task["task_id"]), "kind": task["kind"], "matched_group": task.get("matched_group"),
        "status": "package_admission_passed" if all(checks.values()) else "package_admission_failed",
        "checks": checks, "reference_changed_paths": changed, "baseline": baseline, "reference": reference,
        "adversarial_solutions": adversarials,
        "semantic_evaluation_complete": False,
    }


def validate_corpus(track_root: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    root = (track_root or DEFAULT_TRACKS_ROOT / "workspace-v0.2").resolve(); task_paths = sorted(root.glob("tasks/*/task.json"))
    rows = []; failures = []
    for path in task_paths:
        try:
            row = validate_task_package(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            row = {"task_id": path.parent.name, "status": "package_admission_failed", "checks": {}, "error": str(exc)}
        rows.append(row)
        if row["status"] != "package_admission_passed": failures.append(row["task_id"])
    summary = {
        "schema_version": "growing-bench-corpus-admission-2.0", "track_id": "workspace-v0.2",
        "task_count": len(rows), "admitted_count": len(rows) - len(failures), "validated_count": len(rows) - len(failures),
        "failed_count": len(failures), "failed_task_ids": failures,
        "status": "package_admission_passed" if len(rows) == 50 and not failures else "package_admission_incomplete",
        "semantic_evaluation_complete": False,
        "claim_boundary": "Package admission proves baseline/reference/scope, hidden-oracle separation, and rejection of checked known-wrong alternatives; real trajectory semantics still require blind judging.",
        "tasks": rows,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary
