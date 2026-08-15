from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parse_case(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("case must start with JSON frontmatter between --- lines")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("case frontmatter has no closing ---")
    metadata = json.loads(text[4:end])
    if not isinstance(metadata, dict):
        raise ValueError("case frontmatter must be an object")
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in text[end + 5 :].splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip().casefold()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return metadata, sections


def _criteria(section: str) -> list[str]:
    return [line[2:].strip() for line in section.splitlines() if line.startswith("- ")]


def _kind(metadata: dict[str, Any]) -> str | None:
    domain, context = metadata.get("domain"), metadata.get("review_context")
    if domain in {"code", "writing"}:
        return domain
    if domain == "review" and context in {"internal", "external_peer"}:
        return "internal_review" if context == "internal" else "external_peer_review"
    return None


def _normalized_task(text: str) -> str:
    return " ".join(text.casefold().split())


def preflight(
    case: Path,
    tracks_root: Path = DEFAULT_TRACKS_ROOT,
    catalog: Path = DEFAULT_FIXTURE_CATALOG,
    track: str | None = None,
) -> dict[str, Any]:
    metadata, sections = _parse_case(case)
    case_id = metadata.get("case_id") or case.stem.casefold().replace(" ", "-")
    track_id = track or metadata.get("track_id")
    if not isinstance(case_id, str) or not SLUG.fullmatch(case_id):
        raise ValueError("case_id must be a lowercase slug")
    if not isinstance(track_id, str) or not SLUG.fullmatch(track_id):
        raise ValueError("track_id must be a lowercase slug")
    completion = _criteria(sections.get("completion criteria", ""))
    required = ("title", "domain", "review_context", "environment_family", "source")
    missing = [name for name in required if not metadata.get(name)]
    if not sections.get("task"):
        missing.append("section:Task")
    if not completion:
        missing.append("section:Completion criteria")
    if metadata.get("permission_to_publish") not in {True, False}:
        missing.append("permission_to_publish:true-or-false")
    catalog_value = json.loads(catalog.read_text(encoding="utf-8"))
    environment = catalog_value.get(metadata.get("environment_family"), {})
    kind = _kind(metadata)
    environment_ready = bool(environment.get("built")) and kind in environment.get(
        "supported_kinds", []
    )
    duplicates: list[str] = []
    normalized = _normalized_task(sections.get("task", ""))
    if tracks_root.exists() and normalized:
        for candidate_path in tracks_root.glob("*/staging/*/candidate.json"):
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            other = _normalized_task(candidate.get("sections", {}).get("task", ""))
            if other == normalized:
                duplicates.append(str(candidate_path))
    checks = {
        "information_sufficient": not missing,
        "completion_criteria_present": bool(completion),
        "provenance_present": bool(metadata.get("source")),
        "publication_permission_explicit": metadata.get("permission_to_publish") in {True, False},
        "environment_executable": environment_ready,
        "duplicate_free": not duplicates or bool(metadata.get("supersedes")),
        "pair_metadata_present": bool(metadata.get("pair_id") or metadata.get("variant")),
    }
    status = "ready_for_materialization" if all(
        checks[name]
        for name in (
            "information_sufficient",
            "completion_criteria_present",
            "provenance_present",
            "publication_permission_explicit",
            "environment_executable",
            "duplicate_free",
        )
    ) else "needs_curation"
    return {
        "schema_version": "growing-bench-case-candidate-1.0",
        "case_id": case_id,
        "track_id": track_id,
        "kind": kind,
        "metadata": metadata,
        "sections": sections,
        "completion_criteria": completion,
        "checks": checks,
        "missing": missing,
        "duplicates": duplicates,
        "status": status,
        "reference_status": "silver_pending",
    }


def ingest(
    case: Path,
    tracks_root: Path = DEFAULT_TRACKS_ROOT,
    catalog: Path = DEFAULT_FIXTURE_CATALOG,
    track: str | None = None,
    materialize: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    candidate = preflight(case.resolve(), tracks_root.resolve(), catalog.resolve(), track)
    target = tracks_root.resolve() / candidate["track_id"] / "staging" / candidate["case_id"]
    if target.exists():
        raise FileExistsError(f"case already staged: {target}")
    target.mkdir(parents=True)
    shutil.copyfile(case, target / "case.md")
    candidate_path = target / "candidate.json"
    _write_json(candidate_path, candidate)
    result: dict[str, Any] = {"ingest": {"status": candidate["status"], "candidate": str(candidate_path)}}
    if not (materialize or validate):
        return result
    if candidate["status"] != "ready_for_materialization":
        raise ValueError("case did not pass preflight; inspect candidate.json")
    catalog_value = json.loads(catalog.read_text(encoding="utf-8"))
    environment = catalog_value[candidate["metadata"]["environment_family"]]
    task_dir = tracks_root.resolve() / candidate["track_id"] / "tasks" / candidate["case_id"]
    if task_dir.exists():
        raise FileExistsError(f"task already materialized: {task_dir}")
    task_dir.mkdir(parents=True)
    task = {
        "schema_version": "growing-bench-task-1.0",
        "task_id": f"living-{candidate['track_id']}--{candidate['case_id']}",
        "kind": candidate["kind"],
        "fixture": environment["fixture"],
        "prompt": candidate["sections"]["task"],
        "completion_criteria": candidate["completion_criteria"],
        "checks": environment["checks"],
        "ignore_paths": environment.get("ignore_paths", []),
        "allowed_paths": candidate["metadata"].get("allowed_paths", []),
        "baseline_expectation": environment["baseline_expectation"],
        "expected_failure": environment.get("expected_failure"),
        "living_case": {
            "case_id": candidate["case_id"],
            "track_id": candidate["track_id"],
            "source": candidate["metadata"]["source"],
            "permission_to_publish": candidate["metadata"]["permission_to_publish"],
            "supersedes": candidate["metadata"].get("supersedes"),
            "reference_status": "silver_pending",
        },
    }
    task_path = task_dir / "task.json"
    _write_json(task_path, task)
    shutil.copyfile(case, task_dir / "case.md")
    result["materialize"] = {"status": "materialized", "task": str(task_path)}
    if validate:
        result["validate"] = validate_baseline(task_path, task_dir / "validation.json")
    return result


def _run_checks(task: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    import subprocess

    rows = []
    for check in task["checks"]:
        completed = subprocess.run(
            check["command"], cwd=workspace, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=180, check=False,
        )
        rows.append({
            "name": check["name"], "command": check["command"],
            "returncode": completed.returncode, "passed": completed.returncode == 0,
            "stdout": completed.stdout, "stderr": completed.stderr,
        })
    return rows


def validate_baseline(task_path: Path, output: Path) -> dict[str, Any]:
    task = json.loads(task_path.read_text(encoding="utf-8"))
    fixtures_root = (REPOSITORY_ROOT / "fixtures").resolve()
    fixture = (REPOSITORY_ROOT / task["fixture"]).resolve()
    if not fixture.is_relative_to(fixtures_root) or not fixture.is_dir():
        raise ValueError("fixture must be a real directory inside fixtures/")
    with tempfile.TemporaryDirectory(prefix="growing-bench-validate-") as name:
        workspace = Path(name) / "fixture"
        shutil.copytree(fixture, workspace)
        checks = _run_checks(task, workspace)
    if task["baseline_expectation"] == "passing":
        expectation_met = bool(checks) and all(row["passed"] for row in checks)
    else:
        signature = task.get("expected_failure")
        expectation_met = False
        if isinstance(signature, dict):
            for row in checks:
                visible = f"{row['stdout']}\n{row['stderr']}"
                if (
                    row["name"] == signature.get("check")
                    and row["returncode"] == signature.get("returncode")
                    and signature.get("contains") in visible
                ):
                    expectation_met = True
                    break
    result = {
        "schema_version": "growing-bench-validation-1.0",
        "task_id": task["task_id"],
        "status": "validated" if expectation_met else "validation_failed",
        "fixture_isolated_copy": True,
        "checks": checks,
    }
    _write_json(output, result)
    return result

