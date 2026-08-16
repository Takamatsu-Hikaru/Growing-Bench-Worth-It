from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .pipeline import _criteria, _kind, _parse_case
from .task_contract import load_task


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _source(case: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must name a directory beside the Markdown case")
    path = (case.parent / value).resolve()
    if not path.is_relative_to(case.parent.resolve()) or not path.is_dir():
        raise ValueError(f"{field} must stay inside the contribution directory")
    return path


def preflight_workspace_case(case: Path, tracks_root: Path, track: str | None = None) -> dict[str, Any]:
    case = case.resolve()
    metadata, sections = _parse_case(case)
    case_id = str(metadata.get("case_id") or case.stem)
    track_id = str(track or metadata.get("track_id") or "workspace-community-v0.2")
    missing: list[str] = []
    for key in ("title", "domain", "review_context", "source", "permission_to_publish", "fixture_source", "reference_source", "checks", "allowed_paths"):
        if key not in metadata or metadata[key] in (None, "", []):
            missing.append(key)
    completion = _criteria(sections.get("completion criteria", ""))
    if not sections.get("task"):
        missing.append("section:Task")
    if not completion:
        missing.append("section:Completion criteria")
    fixture = reference = None
    try:
        fixture = _source(case, metadata.get("fixture_source"), "fixture_source")
        reference = _source(case, metadata.get("reference_source"), "reference_source")
    except ValueError as exc:
        missing.append(str(exc))
    checks_ok = isinstance(metadata.get("checks"), list) and all(
        isinstance(row, dict) and isinstance(row.get("command"), list) and row.get("name")
        for row in metadata.get("checks", [])
    )
    if not checks_ok:
        missing.append("checks: named command arrays")
    duplicate = (tracks_root.resolve() / track_id / "tasks" / case_id).exists()
    checks = {
        "information_sufficient": not missing,
        "completion_criteria_observable": bool(completion) and checks_ok,
        "fixture_present": fixture is not None,
        "reference_solution_present": reference is not None,
        "publication_permission": metadata.get("permission_to_publish") is True,
        "duplicate_free": not duplicate or bool(metadata.get("supersedes")),
        "pair_or_standalone_declared": bool(metadata.get("pair_id") or metadata.get("variant") == "standalone"),
    }
    ready = all(checks.values())
    return {
        "schema_version": "growing-bench-workspace-candidate-2.0",
        "case_id": case_id,
        "track_id": track_id,
        "kind": _kind(metadata),
        "metadata": metadata,
        "sections": sections,
        "completion_criteria": completion,
        "checks": checks,
        "missing": sorted(set(missing)),
        "status": "ready_for_ai_curation" if ready else "needs_curation",
    }


def curate_workspace_case(candidate: dict[str, Any], curation: dict[str, Any]) -> dict[str, Any]:
    required = {
        "information_sufficient", "criteria_observable", "provenance_acceptable",
        "publication_allowed", "duplicate_risk", "pairing_possible", "executable",
    }
    if set(curation.get("decisions", {})) != required:
        raise ValueError("AI curation must decide all seven admission questions")
    if curation.get("decision") not in {"admit", "revise", "reject"}:
        raise ValueError("AI curation decision must be admit, revise, or reject")
    if not isinstance(curation.get("rationale"), str) or not curation["rationale"].strip():
        raise ValueError("AI curation requires a rationale")
    return {
        "schema_version": "growing-bench-ai-curation-1.0",
        "case_id": candidate["case_id"],
        "curator_type": "independent_ai",
        "curator_model": curation.get("curator_model", "unspecified"),
        "decision": curation["decision"],
        "decisions": curation["decisions"],
        "rationale": curation["rationale"],
        "unresolved": curation.get("unresolved", []),
    }


def _run_checks(task: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    rows = []
    for check in task["checks"]:
        done = subprocess.run(check["command"], cwd=workspace, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180, check=False)
        rows.append({"name": check["name"], "returncode": done.returncode, "passed": done.returncode == 0, "stdout": done.stdout, "stderr": done.stderr})
    return rows


def _overlay(reference: Path, workspace: Path) -> None:
    for source in reference.rglob("*"):
        if source.is_file():
            target = workspace / source.relative_to(reference)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def materialize_workspace_case(case: Path, tracks_root: Path, curation: dict[str, Any], track: str | None = None) -> dict[str, Any]:
    candidate = preflight_workspace_case(case, tracks_root, track)
    if candidate["status"] != "ready_for_ai_curation":
        raise ValueError("workspace case failed deterministic preflight")
    curated = curate_workspace_case(candidate, curation)
    if curated["decision"] != "admit":
        raise ValueError(f"AI curator decision is {curated['decision']}")
    metadata = candidate["metadata"]
    task_dir = tracks_root.resolve() / candidate["track_id"] / "tasks" / candidate["case_id"]
    if task_dir.exists():
        raise FileExistsError(f"task already materialized: {task_dir}")
    task_dir.mkdir(parents=True)
    shutil.copytree(_source(case.resolve(), metadata["fixture_source"], "fixture_source"), task_dir / "fixture")
    shutil.copytree(_source(case.resolve(), metadata["reference_source"], "reference_source"), task_dir / "reference")
    shutil.copy2(case, task_dir / "case.md")
    (task_dir / "prompt.md").write_text(candidate["sections"]["task"] + "\n", encoding="utf-8", newline="\n")
    criteria = []
    for i, text in enumerate(candidate["completion_criteria"], 1):
        row = {"criterion_id": f"criterion-{i:02d}", "description": text}
        if i == 1:
            row.update({"kind": "check", "check": metadata["checks"][0]["name"]})
        else:
            row.update({"kind": "semantic"})
        criteria.append(row)
    task = {
        "schema_version": "growing-bench-task-2.0",
        "task_id": f"living-{candidate['track_id']}--{candidate['case_id']}",
        "track_id": candidate["track_id"],
        "family_id": metadata.get("pair_id") or candidate["case_id"],
        "variant": metadata.get("variant", "standalone"),
        "kind": candidate["kind"],
        "domain": metadata["domain"],
        "review_context": metadata["review_context"],
        "fixture": "fixture",
        "reference_solution": "reference",
        "prompt_file": "prompt.md",
        "prompt": candidate["sections"]["task"],
        "completion_criteria": criteria,
        "checks": metadata["checks"],
        "ignore_paths": metadata.get("ignore_paths", []),
        "allowed_paths": metadata["allowed_paths"],
        "baseline_expectation": metadata.get("baseline_expectation", "failing"),
        "expected_failure": metadata.get("expected_failure"),
        "source_provenance": {"source": metadata["source"], "permission_to_publish": True},
        "living_case": {"case_id": candidate["case_id"], "curation_status": "ai_admitted", "reference_status": "silver_pending", "supersedes": metadata.get("supersedes")},
    }
    _write(task_dir / "task.json", task)
    _write(task_dir / "curation.json", curated)
    load_task(task_dir / "task.json")
    with tempfile.TemporaryDirectory(prefix="growing-bench-living-") as name:
        baseline = Path(name) / "baseline"; shutil.copytree(task_dir / "fixture", baseline)
        baseline_rows = _run_checks(task, baseline)
        no_op_rejected = not all(row["passed"] for row in baseline_rows)
        solved = Path(name) / "solved"; shutil.copytree(task_dir / "fixture", solved); _overlay(task_dir / "reference", solved)
        reference_rows = _run_checks(task, solved)
    validation = {
        "schema_version": "growing-bench-workspace-admission-1.0",
        "task_id": task["task_id"],
        "status": "validated" if no_op_rejected and all(r["passed"] for r in reference_rows) else "validation_failed",
        "baseline_checks": baseline_rows,
        "no_op_rejected": no_op_rejected,
        "reference_solution_passes": bool(reference_rows) and all(r["passed"] for r in reference_rows),
        "reference_checks": reference_rows,
    }
    _write(task_dir / "validation.json", validation)
    return {"candidate": candidate, "curation": curated, "task": str(task_dir / "task.json"), "validation": validation}


def admit_scored_case(task_dir: Path, score_path: Path, registry: Path, track_version: str) -> dict[str, Any]:
    task = load_task(task_dir / "task.json")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    validation = json.loads((task_dir / "validation.json").read_text(encoding="utf-8"))
    if validation["status"] != "validated" or score.get("task_id") != task["task_id"]:
        raise ValueError("case must have validated workspace evidence and a task-bound score")
    current = json.loads(registry.read_text(encoding="utf-8")) if registry.is_file() else {"schema_version": "growing-bench-living-registry-1.0", "tracks": []}
    if any(row["track_id"] == track_version for row in current["tracks"]):
        raise ValueError("track_id is immutable and already registered")
    row = {"track_id": track_version, "parent_track": task.get("track_id"), "case_ids": [task["living_case"]["case_id"]], "task_ids": [task["task_id"]], "score_file": str(score_path.resolve()), "supersedes": task["living_case"].get("supersedes")}
    current["tracks"].append(row); _write(registry, current)
    return row
