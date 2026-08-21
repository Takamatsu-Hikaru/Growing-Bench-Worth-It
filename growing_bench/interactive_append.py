from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ingest_experience import enrich_preflight
from .quality import find_mojibake
from .run_append import SECRET_PATTERNS, _redact_tree
from .workspace_ingest import preflight_workspace_case


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _slug(value: str) -> str:
    return "-".join("".join(ch.casefold() if ch.isalnum() else " " for ch in value).split())[:72] or "interactive-agent-experience"


def _remove_ignored(root: Path, ignored: list[str]) -> None:
    for relative in ignored:
        target = root / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
    for target in sorted(root.rglob("__pycache__"), reverse=True):
        if target.is_dir():
            shutil.rmtree(target)
    for target in root.rglob("*.pyc"):
        target.unlink()


def append_interactive_run(
    run_dir: Path, output: Path, title: str, *, source_run: str | None = None,
    permission_to_publish: bool = False, redact: bool = False, check: bool = False,
    tracks_root: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = payload.get("results", [])
    candidates = [row for row in rows if source_run is None or row.get("run_name") == source_run]
    if not candidates:
        raise ValueError("requested interactive source run is absent")
    chosen = max(
        candidates,
        key=lambda row: (
            float(row.get("observed_agent_burden_points", 0)),
            int(row.get("stale_narrative_events", 0)),
            -float(row.get("trajectory_value", 0)),
        ),
    )
    peers = [row for row in rows if row["scenario_id"] == chosen["scenario_id"]]
    reference_candidates = [row for row in peers if row["run_name"] != chosen["run_name"]] or peers
    reference = min(
        reference_candidates,
        key=lambda row: (
            -float(row.get("task_success", 0)),
            float(row.get("observed_agent_burden_points", 0)),
            -float(row.get("trajectory_value", 0)),
        ),
    )
    source = run_dir / "runs" / chosen["run_name"]
    reference_source = run_dir / "runs" / reference["run_name"]
    output.mkdir(parents=True)
    shutil.copytree(source / "before", output / "fixture")
    shutil.copytree(reference_source / "workspace", output / "reference")
    for filename in ("scenario.json", "task.json", "trajectory.jsonl", "controller.jsonl", "changes.diff"):
        if (source / filename).is_file():
            shutil.copy2(source / filename, output / filename)
    judgments = output / "judgments"
    judgments.mkdir()
    for kind in ("actions", "interaction"):
        origin = run_dir / "judgments" / chosen["run_name"] / kind / "consensus.json"
        if origin.is_file():
            shutil.copy2(origin, judgments / f"{kind}.json")
    task = json.loads((source / "task.json").read_text(encoding="utf-8"))
    scenario = json.loads((source / "scenario.json").read_text(encoding="utf-8"))
    ignored = list(task.get("ignore_paths", []))
    _remove_ignored(output / "fixture", ignored)
    _remove_ignored(output / "reference", ignored)
    case_id = _slug(title)
    metadata = {
        "case_id": case_id, "track_id": f"interactive-community-{datetime.now(timezone.utc):%Y-%m}",
        "title": title, "domain": "review" if task["kind"] in {"internal_review", "external_peer_review"} else task["kind"],
        "review_context": "internal" if task["kind"] == "internal_review" else "external_peer" if task["kind"] == "external_peer_review" else "not_applicable",
        "source": f"Interactive self-test {chosen['run_name']}",
        "permission_to_publish": permission_to_publish, "variant": "standalone",
        "fixture_source": "fixture", "reference_source": "reference",
        "allowed_paths": task["allowed_paths"], "checks": task["checks"],
        "baseline_expectation": task["baseline_expectation"], "expected_failure": task.get("expected_failure"),
        "ignore_paths": task.get("ignore_paths", []), "interaction_scenario": "scenario.json",
    }
    signal_lines = [
        f"- {row['signal_id']}: {row['status']} — {row['explanation']}"
        for row in chosen["interaction_judgment"]["signals"]
    ]
    text = (
        "---\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n---\n\n"
        "## Task\n\n" + task["prompt"].strip() + "\n\n"
        "## Completion criteria\n\n" + "\n".join(f"- {row.get('description', row.get('criterion_id', 'Complete the task'))}" for row in task.get("completion_criteria", []) if isinstance(row, dict)) + "\n\n"
        "## Interaction controller\n\n" + "\n".join(
            f"- {turn['role']}: {turn['message']}" for turn in scenario["turns"]
        ) + "\n\n## Observed interaction signals\n\n" + "\n".join(signal_lines) +
        "\n\n## Why this case is useful\n\nThis case preserves the runnable workspace, user updates, full visible trajectory, and a lower-burden comparison run so future Agents can be regression-tested on the same interaction boundary.\n"
    )
    (output / "case.md").write_text(text, encoding="utf-8", newline="\n")
    comparison = {
        "schema_version": "growing-bench-interactive-appended-comparison-1.0",
        "scenario_id": chosen["scenario_id"], "selected_run": chosen["run_name"],
        "reference_run": reference["run_name"],
        "runs": [{
            "run_name": row["run_name"], "condition": row["condition"],
            "task_success": row.get("task_success"), "trajectory_roi": row.get("trajectory_roi"),
            "state_update_success": row.get("state_update_success"),
            "stale_narrative_events": row.get("stale_narrative_events"),
            "scenario_pressure": row.get("scenario_pressure"),
            "observed_agent_burden_points": row.get("observed_agent_burden_points"),
        } for row in peers],
    }
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
        "schema_version": "growing-bench-interactive-appended-case-1.0",
        "status": "ready_for_curation" if permission_to_publish and not issues else "local_draft",
        "case": str(output / "case.md"), "source_run": chosen["run_name"],
        "reference_run": reference["run_name"], "publication_permission": permission_to_publish,
        "redactions": replacements, "issues": issues, "preflight": preflight,
    }
    _write_json(output / "append.json", result)
    return result
