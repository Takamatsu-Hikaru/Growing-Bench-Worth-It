from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ingest_experience import enrich_preflight
from .quality import find_mojibake
from .workspace_ingest import preflight_workspace_case


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"']+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s\"']+"),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (result or "agent-experience")[:72]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _redact_tree(root: Path) -> int:
    replacements = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = text
        for pattern in SECRET_PATTERNS:
            updated, count = pattern.subn(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", updated)
            replacements += count
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
    return replacements


def _copy_reference(source_run: Path, task: dict[str, Any], target: Path) -> list[str]:
    changes = json.loads((source_run / "changes.json").read_text(encoding="utf-8"))
    copied = []
    for relative in changes.get("changed_paths", []):
        if not any(relative == root.rstrip("/") or relative.startswith(root.rstrip("/") + "/") for root in task["allowed_paths"]):
            continue
        source = source_run / "workspace" / relative
        if source.is_file():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
    return copied


def append_run(
    run_dir: Path,
    output: Path,
    title: str,
    *,
    source_run: str | None = None,
    redact: bool = False,
    check: bool = False,
    permission_to_publish: bool = False,
    tracks_root: Path | None = None,
) -> dict[str, Any]:
    run_dir, output = run_dir.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"append output already exists: {output}")
    payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("append expects a self-test results directory")
    candidates = [row for row in rows if source_run is None or row.get("run_name") == source_run]
    if not candidates:
        raise ValueError("requested source run is absent from self-test results")
    chosen = max(
        candidates,
        key=lambda row: sum(1 for value in row.get("action_categories", {}).values() if value == "avoidable") + sum(1 for value in row.get("action_categories", {}).values() if value == "missed"),
    )
    task_id = chosen["task_id"]
    same_task = [row for row in rows if row["task_id"] == task_id]
    reference_row = max(same_task, key=lambda row: (float(row.get("task_success", 0)), float(row.get("trajectory_value", 0))))
    bad_run = run_dir / "runs" / chosen["run_name"]
    reference_run = run_dir / "runs" / reference_row["run_name"]
    task = json.loads((bad_run / "task.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    shutil.copytree(bad_run / "before", output / "fixture")
    (output / "reference").mkdir()
    reference_files = _copy_reference(reference_run, task, output / "reference")
    if not reference_files:
        raise ValueError("the selected reference run has no allowed changed files")
    bad_actions = []
    for action in chosen.get("actions", []):
        info = chosen.get("action_explanations", {}).get(action["action_id"], {})
        if info.get("label") in {"avoidable", "missed", "unresolved"}:
            bad_actions.append(f"- {action['description']}: {info.get('explanation') or info.get('omission_consequence') or info.get('label')}")
    case_id = _slug(title)
    track_id = f"workspace-community-{datetime.now(timezone.utc):%Y-%m}"
    criteria = [
        row.get("description", row.get("criterion_id", "Complete the task"))
        for row in task.get("completion_criteria", []) if isinstance(row, dict)
    ]
    metadata = {
        "case_id": case_id,
        "track_id": track_id,
        "title": title,
        "domain": "review" if task["kind"] in {"internal_review", "external_peer_review"} else task["kind"],
        "review_context": "internal" if task["kind"] == "internal_review" else "external_peer" if task["kind"] == "external_peer_review" else "not_applicable",
        "environment_family": "portable_workspace_package",
        "source": f"Growing Bench self-test run {chosen['run_name']}",
        "permission_to_publish": permission_to_publish,
        "variant": "standalone",
        "fixture_source": "fixture",
        "reference_source": "reference",
        "allowed_paths": task["allowed_paths"],
        "checks": task["checks"],
        "baseline_expectation": task["baseline_expectation"],
        "expected_failure": task.get("expected_failure"),
        "ignore_paths": task.get("ignore_paths", []),
    }
    text = (
        "---\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n---\n\n"
        "## Task\n\n" + task["prompt"].strip() + "\n\n"
        "## Completion criteria\n\n" + "\n".join(f"- {row}" for row in criteria) + "\n\n"
        "## Observed bad response\n\n" + ("\n".join(bad_actions) if bad_actions else "- Review the attached trajectory and action judgment.") + "\n\n"
        "## Why this is a problem\n\nThe selected trajectory contains work that the action evaluator marked avoidable, missed, or unresolved. The contribution preserves the smallest runnable workspace for curation.\n"
    )
    (output / "case.md").write_text(text, encoding="utf-8", newline="\n")
    shutil.copy2(bad_run / "trajectory.jsonl", output / "trajectory.jsonl")
    shutil.copy2(run_dir / "judgments" / chosen["run_name"] / "consensus.json", output / "judgment.json")
    comparison = {"schema_version": "growing-bench-appended-comparison-1.0", "task_id": task_id, "selected_run": chosen["run_name"], "reference_run": reference_row["run_name"], "runs": []}
    for row in same_task:
        condition = row.get("condition", "unknown")
        evidence_dir = output / "evidence" / condition
        evidence_dir.mkdir(parents=True, exist_ok=True)
        source = run_dir / "runs" / row["run_name"]
        judge_source = run_dir / "judgments" / row["run_name"] / "consensus.json"
        shutil.copy2(source / "trajectory.jsonl", evidence_dir / "trajectory.jsonl")
        if judge_source.is_file():
            shutil.copy2(judge_source, evidence_dir / "judgment.json")
        comparison["runs"].append({"condition": condition, "run_name": row["run_name"], "task_success": row.get("task_success"), "necessary_action_recall": row.get("necessary_action_recall"), "action_categories": row.get("action_categories", {}), "observed": row.get("observed", {})})
    _write_json(output / "comparison.json", comparison)

    replacements = _redact_tree(output) if redact else 0
    issues = []
    for path in output.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if find_mojibake(content):
            issues.append({"code": "encoding_damage", "path": str(path.relative_to(output)), "message": "Replacement characters were detected.", "next_step": "Repair the source text before admission."})
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            issues.append({"code": "possible_secret", "path": str(path.relative_to(output)), "message": "A credential-like value was detected.", "next_step": "Run append with --redact or remove it manually."})
    preflight = None
    if check:
        root = tracks_root.resolve() if tracks_root else output.parent / "tracks-check"
        preflight = enrich_preflight(preflight_workspace_case(output / "case.md", root), output / "case.md")
    result = {
        "schema_version": "growing-bench-appended-case-1.0",
        "status": "ready_for_curation" if not issues and permission_to_publish else "local_draft",
        "case": str(output / "case.md"),
        "source_run": chosen["run_name"],
        "reference_run": reference_row["run_name"],
        "reference_files": reference_files,
        "redactions": replacements,
        "issues": issues,
        "preflight": preflight,
        "publication_permission": permission_to_publish,
    }
    _write_json(output / "append.json", result)
    return result
