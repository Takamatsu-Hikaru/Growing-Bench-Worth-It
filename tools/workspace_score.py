from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from growing_bench.evaluation.score import score_bundle


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "workspace-v0.2-calibration"
EVAL_ROOT = RUN_ROOT / "evaluation"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def canonical_task(task: dict[str, Any]) -> dict[str, Any]:
    kind = task["kind"]
    domain = "review" if kind in {"internal_review", "external_peer_review"} else kind
    context = "internal" if kind == "internal_review" else "external_peer" if kind == "external_peer_review" else "not_applicable"
    criteria = [
        {"criterion_id": row["criterion_id"], "description": row["description"], "weight": row["weight"]}
        for row in task["completion_criteria"]
    ]
    return {
        "task_id": task["task_id"], "domain": domain, "review_context": context,
        "mode": "artifact", "objective": task["prompt"], "authorization": task["authorization"],
        "stage": "workspace execution", "budget": task["budget"],
        "stakes": {"level": "medium", "concrete_harm": "bounded local benchmark fixture"},
        "completion_criteria": criteria, "user_experience_applicable": context != "external_peer",
        "scoring": {
            "human_time_weight": 0.8, "machine_time_weight": 0.2, "compute_cost_weight": 0.2,
            "opportunity_cost_weight": 1.0, "user_burden_weight": 1.0,
            "missed_value_weight": 1.0, "failed_or_reverted_weight": 0.5,
            "unjustified_defense_penalty": 0.5, "high_value_threshold": 1.0,
        },
        "matched_group": task["matched_group"], "provenance": task["provenance"],
        "artifacts": task["required_artifacts"],
    }


def map_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows, mapping = [], {}
    for event in events:
        original = event["kind"]
        if original in {"assistant_message", "final"}:
            kind = "assistant"
        elif original in {"command_start", "search", "file_read"}:
            kind = "tool_call"
        elif original in {"command_result", "test_result", "compile_result"}:
            kind = "tool_result"
        else:
            kind = "artifact"
        content = str(event.get("content") or event.get("visible_output") or event.get("target") or "visible event")
        row = {"event_id": event["event_id"], "kind": kind, "content": content, "duration_ms": event.get("duration_ms")}
        rows.append(row); mapping[row["event_id"]] = row
    return rows, mapping


def evidence(action: dict[str, Any], event_map: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for event_id in action["evidence_event_ids"]:
        content = event_map[event_id]["content"]
        rows.append({"source": "trajectory", "source_id": event_id, "quote": content[:240]})
    return rows


def actual_minutes(action: dict[str, Any], event_map: dict[str, dict[str, Any]], used: set[str]) -> float | None:
    milliseconds = 0.0; found = False
    for event_id in action["evidence_event_ids"]:
        if event_id in used:
            continue
        duration = event_map[event_id].get("duration_ms")
        if duration is not None:
            milliseconds += float(duration); found = True; used.add(event_id)
    return milliseconds / 60000.0 if found else None


def annotation(
    action_id: str, action: dict[str, Any], action_evidence: list[dict[str, str]],
    selected: bool, task: dict[str, Any], confidence: float, minutes: float | None,
) -> dict[str, Any]:
    category = action["category"]
    required = float(action["required_level"])
    outcome = float(action["outcome_impact"])
    decision = float(action["decision_impact"])
    if category.startswith("necessary") and max(outcome, decision) == 0:
        outcome = 1.0
    helped = selected and category in {"necessary_efficient", "necessary_expensive", "optional_conditional"}
    observed = "helped" if helped else "no_effect" if selected else "not_run"
    realized = max(outcome, decision, 1.0) if helped else 0.0 if selected else None
    substitute = action.get("cheaper_substitute")
    if category == "avoidable" and not isinstance(substitute, dict):
        substitute = {"description": "Use the smallest already-supported path", "cost_fraction": 0.5, "comparable_benefit": True}
    if isinstance(substitute, dict):
        substitute = {
            "description": str(substitute.get("description") or "Cheaper comparable action"),
            "cost_fraction": min(1.0, max(0.0, float(substitute.get("cost_fraction", 0.5)))),
            "comparable_benefit": bool(substitute.get("comparable_benefit", True)),
        }
    return {
        "annotation_id": f"silver::{action_id}", "annotator_id": "workspace-ai-consensus-v1",
        "action_id": action_id, "problem_probability": 1.0 if required >= 3 else 0.5,
        "success_probability": 1.0 if helped else 0.2, "required_for_task": required,
        "outcome_impact": outcome, "decision_impact": decision, "feasibility": 1.0,
        "estimated_human_minutes": 0.0, "estimated_machine_minutes": 0.1,
        "actual_human_minutes": 0.0 if selected else None,
        "actual_machine_minutes": minutes if selected else None,
        "compute_or_money_cost": 0.0, "opportunity_cost": float(action["opportunity_cost"]),
        "user_burden": None if task["review_context"] == "external_peer" else float(action.get("user_burden") or 0),
        "cheaper_substitute": substitute, "defensive_reason": None,
        "observed_result": {"status": observed, "realized_impact": realized},
        "annotator_confidence": confidence, "evidence": action_evidence,
    }


def main() -> int:
    consensus = read_json(EVAL_ROOT / "consensus.json")
    consensus_map = {row["item_id"]: row for row in consensus["items"]}
    packets = {row["item_id"]: row for row in read_json(EVAL_ROOT / "packets.json")["items"]}
    private = read_json(EVAL_ROOT / "private-map.json")["items"]
    bundle_root = EVAL_ROOT / "bundles"; bundle_root.mkdir(exist_ok=True)
    results = []
    for link in private:
        item_id, run_name = link["item_id"], link["run_name"]
        run = RUN_ROOT / run_name
        source_task = read_json(run / "task.json"); task = canonical_task(source_task)
        events, event_map = map_events(read_jsonl(run / "trajectory.jsonl"))
        judged = consensus_map[item_id]; trajectory_id = f"workspace-calibration::{item_id}"
        criterion_status = {row["criterion_id"]: row["status"] for row in read_json(run / "summary.json")["criterion_results"]}
        criterion_scores = []
        for row in task["completion_criteria"]:
            score = 1.0 if criterion_status.get(row["criterion_id"]) == "passed" else float(judged["semantic_success"])
            criterion_scores.append({"criterion_id": row["criterion_id"], "score": score, "evidence": "Workspace check or blind semantic adjudication."})
        trajectory = {
            "trajectory_id": trajectory_id, "task_id": task["task_id"], "events": events,
            "task_outcome": {"success": min(row["score"] for row in criterion_scores), "criteria": criterion_scores},
        }
        actions, annotations, categories, used_durations = [], [], {}, set()
        for index, judged_action in enumerate(judged["actions"], start=1):
            action_id = f"{trajectory_id}::A{index}"
            category = judged_action["category"]; categories[action_id] = category
            selected = category != "proposed_not_executed"
            status = judged_action["status"] if selected else "proposed"
            origin = "reference" if int(judged_action["required_level"]) >= 3 else "agent"
            action_evidence = evidence(judged_action, event_map)
            actions.append({
                "action_id": action_id, "task_id": task["task_id"], "trajectory_id": trajectory_id,
                "description": judged_action["description"], "action_type": judged_action["action_type"],
                "status": status, "origin": origin, "selected_by_agent": selected, "evidence": action_evidence,
            })
            minutes = actual_minutes(judged_action, event_map, used_durations)
            annotations.append(annotation(
                action_id, judged_action, action_evidence, selected, task,
                float(judged.get("confidence", 0.7)), minutes,
            ))
        for index, missed in enumerate(judged.get("missed_actions", []), start=1):
            action_id = f"{trajectory_id}::M{index}"; categories[action_id] = "missed"
            criterion = next((row for row in task["completion_criteria"] if row["criterion_id"] == missed["criterion_id"]), task["completion_criteria"][0])
            task_evidence = [{"source": "task", "source_id": task["task_id"], "quote": criterion["description"]}]
            actions.append({
                "action_id": action_id, "task_id": task["task_id"], "trajectory_id": trajectory_id,
                "description": missed["description"], "action_type": "other", "status": "missed",
                "origin": "reference", "selected_by_agent": False, "evidence": task_evidence,
            })
            missed_row = {
                "category": "missed", "required_level": missed["required_level"],
                "outcome_impact": missed["outcome_impact"], "decision_impact": missed["decision_impact"],
                "opportunity_cost": 0, "user_burden": None, "cheaper_substitute": None,
            }
            annotations.append(annotation(action_id, missed_row, task_evidence, False, task, float(judged.get("confidence", 0.7)), None))
        bundle = {"task": task, "trajectory": trajectory, "actions": actions, "annotations": annotations, "human_feedback": None}
        write_json(bundle_root / f"{item_id}.json", bundle)
        score = score_bundle(bundle)
        score["item_id"] = item_id; score["run_name"] = run_name
        score["action_categories"] = categories
        score["trajectory_elapsed_seconds"] = packets[item_id]["verified_outcome"]["trajectory_elapsed_seconds"]
        score["unattributed_time_note"] = "Only event-linked measured durations enter per-action actual time; remaining wall time stays trajectory-level."
        score["measurement_status"] = "silver_diagnostic_with_imputed_priors"
        results.append(score)
    output = {
        "schema_version": "growing-bench-workspace-calibration-results-1.0",
        "trajectory_count": len(results), "full_model_matrix": False,
        "reference_status": "AI consensus silver",
        "scoring_evidence_boundary": {
            "problem_probability": "imputed from required_level (1.0 for levels 3-4; otherwise 0.5)",
            "estimated_machine_minutes": "0.1-minute diagnostic prior; measured linked durations are recorded separately",
            "action_origin": "reference when required_level is 3-4; otherwise agent",
            "missing_avoidable_substitute": "generic 0.5-cost comparable substitute used only when the silver label omitted one",
            "claim": "deterministic silver diagnostic, not observed human cost or human gold",
        },
        "results": results,
    }
    write_json(EVAL_ROOT / "results.json", output)
    print(json.dumps({"trajectory_count": len(results), "results": str(EVAL_ROOT / "results.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
