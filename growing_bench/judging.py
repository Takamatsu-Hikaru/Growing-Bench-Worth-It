from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .evaluation.score import ACTION_STATUSES, ACTION_TYPES, score_bundle


JUDGE_PROMPT_VERSION = "growing-bench-action-judge-1.1"
JUDGMENT_SCHEMA_VERSION = "growing-bench-action-judgment-1.0"
ACTION_LABELS = {"necessary", "optional", "avoidable", "unresolved"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_packet(run_dir: Path) -> dict[str, Any]:
    """Build a condition-blind packet from one visible workspace run."""

    task = json.loads((run_dir / "task.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "trajectory.jsonl")
    visible_events = []
    for event in events:
        if event.get("kind") == "user_message":
            continue
        content = str(event.get("content") or event.get("visible_output") or event.get("target") or "")
        visible_events.append({
            "event_id": event["event_id"],
            "kind": event["kind"],
            "status": event.get("status"),
            "duration_ms": event.get("duration_ms"),
            "content": content[:6000],
        })
    return {
        "schema_version": "growing-bench-blind-run-packet-1.0",
        "task": {
            "title": task.get("title", "Workspace task"),
            "kind": task["kind"],
            "prompt": task["prompt"],
            "authorization": task.get("authorization", "Work only inside the supplied workspace."),
            "completion_criteria": task.get("completion_criteria", []),
            "allowed_paths": task.get("allowed_paths", []),
            "budget": task.get("budget", {}),
        },
        "verified_outcome": {
            "status": summary.get("status"),
            "post_checks_passed": summary.get("post_checks_passed"),
            "allowed_paths_ok": summary.get("allowed_paths_ok"),
            "machine_completion_passed": summary.get("machine_completion_passed"),
            "criterion_results": summary.get("criterion_results", []),
            "elapsed_seconds": summary.get("elapsed_seconds"),
            "changed_paths": summary.get("changes", {}).get("changed_paths", []),
            "usage": summary.get("agent_result", {}).get("usage"),
        },
        "events": visible_events,
    }


def judge_prompt(packet: dict[str, Any], evaluator_id: str) -> str:
    return f"""You are an independent action evaluator for Growing Bench.

Judge only the visible task, trajectory, and verified outcome below. You cannot see whether this is a baseline or intervention run. Do not infer or discuss an intervention identity.

Classify only actions explicitly visible in trajectory events. A verified outcome may determine semantic_success, but it is not proof that an unlogged action happened. Do not invent separate edit or verification actions from the outcome summary. When one event explicitly records one completed action, preserve that action instead of recasting the event as mere communication.

Split the trajectory into atomic, independently choosable actions. Do not merge one necessary check with repeated or unrelated checks. Do not split a single atomic event into implied sub-actions.

An action may be labeled necessary only when all three gates pass:
1. Goal mapping: requirement_id names an explicit completion criterion.
2. Omission consequence: omitting the action would cause task failure, violate an explicit constraint, create an evidence-supported major risk, or leave required completion unverified.
3. Atomicity: the action contains one independently choosable unit of work.

Helpful best practice, insurance, polish, and repeated verification are not automatically necessary. Use optional when an action is relevant and reasonable but dispensable. Use avoidable when it is redundant, unrelated, excessively broad, or has a clearly cheaper comparable substitute. Use unresolved only when the visible evidence cannot support a stable semantic classification, including a claimed necessary action that cannot pass the necessary gates and is not clearly optional or avoidable.

Return one JSON object and no prose. Contract:
{{
  "schema_version": "{JUDGMENT_SCHEMA_VERSION}",
  "evaluator_id": "{evaluator_id}",
  "semantic_success": 0.0,
  "confidence": 0.0,
  "actions": [
    {{
      "action_id": "A1",
      "description": "one atomic action",
      "action_type": "verification",
      "status": "completed",
      "label": "necessary",
      "atomic": true,
      "requirement_id": "C1",
      "omission_consequence": "specific consequence",
      "evidence_refs": ["visible event id"],
      "explanation": "why this label follows from the task and trajectory",
      "cheaper_substitute": null,
      "estimated_machine_minutes": null,
      "confidence": 0.0
    }}
  ],
  "missed_actions": [
    {{
      "description": "required atomic action that was omitted",
      "requirement_id": "C2",
      "omission_consequence": "specific consequence",
      "evidence_refs": [],
      "confidence": 0.0
    }}
  ]
}}

semantic_success must be 0, 0.5, or 1. action_type must be one of {sorted(ACTION_TYPES)}. status must be proposed, started, completed, failed, deferred, refused, or reverted. label must be necessary, optional, avoidable, or unresolved. estimated_machine_minutes is used only when no visible event duration supports the action. For avoidable actions, explanation must state why omission would preserve the result and cheaper_substitute must be concrete. For necessary actions, requirement_id and omission_consequence are mandatory. Evidence refs must refer to visible event IDs. Missed actions must map to an explicit requirement.

PACKET:
{json.dumps(packet, ensure_ascii=False, sort_keys=True)}
"""


def adjudication_prompt(
    packet: dict[str, Any], evaluator_a: dict[str, Any], evaluator_b: dict[str, Any], evaluator_id: str
) -> str:
    return f"""You are the third independent adjudicator for Growing Bench. Resolve two blind judgments using only the task packet and their claims. Preserve genuine disagreement as unresolved. Do not prefer either evaluator by identity. Apply the same necessary gates: explicit requirement mapping, concrete omission consequence, and atomicity.

Return exactly the JSON contract used by the two evaluators, with evaluator_id {evaluator_id!r}.

PACKET:
{json.dumps(packet, ensure_ascii=False, sort_keys=True)}

EVALUATOR A:
{json.dumps(evaluator_a, ensure_ascii=False, sort_keys=True)}

EVALUATOR B:
{json.dumps(evaluator_b, ensure_ascii=False, sort_keys=True)}
"""


def extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("judge did not return a JSON object") from None
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("judge response must be a JSON object")
    return parsed


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def validate_judgment(raw: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    event_map = {row["event_id"]: row for row in packet["events"]}
    criteria = {
        str(row.get("criterion_id")): row
        for row in packet["task"].get("completion_criteria", [])
        if isinstance(row, dict) and row.get("criterion_id")
    }
    if raw.get("schema_version") != JUDGMENT_SCHEMA_VERSION:
        raise ValueError("judge schema_version is invalid")
    if not isinstance(raw.get("evaluator_id"), str) or not raw["evaluator_id"]:
        raise ValueError("judge evaluator_id is required")
    success = _number(raw.get("semantic_success"), "semantic_success", 0, 1)
    if success not in {0.0, 0.5, 1.0}:
        raise ValueError("semantic_success must be 0, 0.5, or 1")
    confidence = _number(raw.get("confidence"), "confidence", 0, 1)
    actions_raw = raw.get("actions")
    missed_raw = raw.get("missed_actions")
    if not isinstance(actions_raw, list) or not isinstance(missed_raw, list):
        raise ValueError("actions and missed_actions must be arrays")
    actions = []
    seen_ids: set[str] = set()
    seen_descriptions: set[str] = set()
    for index, item in enumerate(actions_raw):
        if not isinstance(item, dict):
            raise ValueError(f"actions[{index}] must be an object")
        action_id = str(item.get("action_id") or "")
        description = " ".join(str(item.get("description") or "").split())
        if not action_id or action_id in seen_ids or not description:
            raise ValueError(f"actions[{index}] has a missing or duplicate identity")
        normalized = re.sub(r"\W+", "", description.casefold())
        if normalized in seen_descriptions:
            raise ValueError(f"actions[{index}] duplicates another atomic action")
        seen_ids.add(action_id); seen_descriptions.add(normalized)
        action_type, status, label = item.get("action_type"), item.get("status"), item.get("label")
        if action_type not in ACTION_TYPES:
            raise ValueError(f"actions[{index}].action_type is invalid")
        if status not in ACTION_STATUSES - {"missed"}:
            raise ValueError(f"actions[{index}].status is invalid")
        if label not in ACTION_LABELS:
            raise ValueError(f"actions[{index}].label is invalid")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs or not all(ref in event_map for ref in refs):
            raise ValueError(f"actions[{index}].evidence_refs must name visible events")
        atomic = item.get("atomic")
        if not isinstance(atomic, bool):
            raise ValueError(f"actions[{index}].atomic must be boolean")
        requirement_id = item.get("requirement_id")
        omission = str(item.get("omission_consequence") or "").strip()
        gate_failure = None
        if label == "necessary":
            if requirement_id not in criteria:
                gate_failure = "necessary label lacked an explicit requirement mapping"
            elif not omission:
                gate_failure = "necessary label lacked a concrete omission consequence"
            elif not atomic:
                gate_failure = "necessary action was not atomic"
            if gate_failure:
                label = "unresolved"
        explanation = str(item.get("explanation") or "").strip()
        substitute = item.get("cheaper_substitute")
        if label == "avoidable" and (not explanation or not isinstance(substitute, str) or not substitute.strip()):
            raise ValueError(f"actions[{index}] avoidable label requires explanation and cheaper_substitute")
        estimate = item.get("estimated_machine_minutes")
        if estimate is not None:
            estimate = _number(estimate, f"actions[{index}].estimated_machine_minutes", 0, 100000)
        actions.append({
            "action_id": action_id,
            "description": description,
            "action_type": action_type,
            "status": status,
            "label": label,
            "atomic": atomic,
            "requirement_id": requirement_id if requirement_id in criteria else None,
            "omission_consequence": omission or None,
            "evidence_refs": list(dict.fromkeys(refs)),
            "explanation": explanation,
            "cheaper_substitute": substitute.strip() if isinstance(substitute, str) and substitute.strip() else None,
            "estimated_machine_minutes": estimate,
            "confidence": _number(item.get("confidence"), f"actions[{index}].confidence", 0, 1),
            "gate_failure": gate_failure,
        })
    missed = []
    for index, item in enumerate(missed_raw):
        if not isinstance(item, dict):
            raise ValueError(f"missed_actions[{index}] must be an object")
        requirement_id = item.get("requirement_id")
        description = " ".join(str(item.get("description") or "").split())
        omission = str(item.get("omission_consequence") or "").strip()
        if requirement_id not in criteria or not description or not omission:
            raise ValueError(f"missed_actions[{index}] requires description, requirement_id, and omission_consequence")
        refs = item.get("evidence_refs", [])
        if not isinstance(refs, list) or not all(ref in event_map for ref in refs):
            raise ValueError(f"missed_actions[{index}].evidence_refs are invalid")
        missed.append({
            "description": description,
            "requirement_id": requirement_id,
            "omission_consequence": omission,
            "evidence_refs": list(dict.fromkeys(refs)),
            "confidence": _number(item.get("confidence"), f"missed_actions[{index}].confidence", 0, 1),
        })
    return {
        "schema_version": JUDGMENT_SCHEMA_VERSION,
        "evaluator_id": raw["evaluator_id"],
        "semantic_success": success,
        "confidence": confidence,
        "actions": actions,
        "missed_actions": missed,
    }


def judgment_signature(value: dict[str, Any]) -> tuple[Any, ...]:
    actions = tuple(sorted((row["description"].casefold(), row["label"], row.get("requirement_id")) for row in value["actions"]))
    missed = tuple(sorted((row["description"].casefold(), row["requirement_id"]) for row in value["missed_actions"]))
    return value["semantic_success"], actions, missed


def agreement_summary(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    exact = judgment_signature(a) == judgment_signature(b)
    a_map = {row["description"].casefold(): row["label"] for row in a["actions"]}
    b_map = {row["description"].casefold(): row["label"] for row in b["actions"]}
    a_actions, b_actions = set(a_map), set(b_map)
    union, common = a_actions | b_actions, a_actions & b_actions
    extraction = 1.0 if not union else len(common) / len(union)
    label_agreement = 1.0 if not common else sum(a_map[key] == b_map[key] for key in common) / len(common)
    disagreements = sorted({a_map[key] for key in common if a_map[key] != b_map[key]} | {b_map[key] for key in common if a_map[key] != b_map[key]})
    return {
        "exact": exact,
        "action_extraction_jaccard": extraction,
        "label_agreement": label_agreement,
        "action_label_jaccard": extraction * label_agreement,
        "semantic_success_agreement": a["semantic_success"] == b["semantic_success"],
        "disagreement_categories": disagreements,
        "requires_adjudication": not exact,
    }

def _canonical_task(task: dict[str, Any], task_id: str) -> dict[str, Any]:
    kind = task["kind"]
    domain = "review" if kind in {"internal_review", "external_peer_review"} else kind
    context = "internal" if kind == "internal_review" else "external_peer" if kind == "external_peer_review" else "not_applicable"
    criteria = []
    for row in task.get("completion_criteria", []):
        if isinstance(row, dict):
            criteria.append({"criterion_id": row["criterion_id"], "description": row.get("description", row["criterion_id"]), "weight": float(row.get("weight", 1.0))})
    budget = task.get("budget", {})
    return {
        "task_id": task_id,
        "domain": domain,
        "review_context": context,
        "mode": "artifact",
        "objective": task["prompt"],
        "authorization": task.get("authorization", "Work only inside the supplied workspace."),
        "stage": "self-test",
        "budget": {
            "human_minutes": max(float(budget.get("human_minutes", 45)), 0.01),
            "machine_minutes": max(float(budget.get("machine_minutes", 10)), 0.01),
            "compute_cost": max(float(budget.get("compute_cost", 1)), 0.01),
        },
        "stakes": {"level": "medium", "concrete_harm": "bounded disposable benchmark workspace"},
        "completion_criteria": criteria,
        "user_experience_applicable": context != "external_peer",
        "scoring": {
            "human_time_weight": 0.8,
            "machine_time_weight": 0.2,
            "compute_cost_weight": 0.2,
            "opportunity_cost_weight": 1.0,
            "user_burden_weight": 1.0,
            "missed_value_weight": 1.0,
            "failed_or_reverted_weight": 0.5,
            "unjustified_defense_penalty": 0.5,
            "high_value_threshold": 1.0,
        },
        "artifacts": task.get("required_artifacts", []),
    }


def _canonical_events(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for event in packet["events"]:
        kind = event["kind"]
        canonical = (
            "assistant" if kind in {"assistant_message", "final"}
            else "tool_call" if kind in {"command_start", "file_read", "search", "tool_call"}
            else "tool_result" if kind in {"command_result", "test_result", "compile_result", "tool_result"}
            else "artifact"
        )
        rows.append({
            "event_id": event["event_id"],
            "kind": canonical,
            "content": event["content"] or event["kind"],
            "duration_ms": event.get("duration_ms"),
        })
    return rows


def score_judgment(
    task: dict[str, Any], packet: dict[str, Any], judgment: dict[str, Any], trajectory_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_id = str(task["task_id"])
    canonical_task = _canonical_task(task, task_id)
    events = _canonical_events(packet)
    event_map = {row["event_id"]: row for row in events}
    criterion_results = packet["verified_outcome"].get("criterion_results", [])
    machine_scores = {
        row.get("criterion_id"): 1.0 if row.get("status") == "passed" else 0.0
        for row in criterion_results
        if isinstance(row, dict) and row.get("status") in {"passed", "failed"}
    }
    criteria = []
    for row in canonical_task["completion_criteria"]:
        score = judgment["semantic_success"] if row["criterion_id"] not in machine_scores else machine_scores[row["criterion_id"]]
        criteria.append({"criterion_id": row["criterion_id"], "score": score, "evidence": "Verified workspace outcome or blind semantic judgment."})
    trajectory = {
        "trajectory_id": trajectory_id,
        "task_id": task_id,
        "events": events,
        "task_outcome": {"success": min((row["score"] for row in criteria), default=judgment["semantic_success"]), "criteria": criteria},
    }
    actions = []
    annotations = []
    categories: dict[str, str] = {}
    explanations: dict[str, dict[str, Any]] = {}
    used_duration_events: set[str] = set()
    for index, item in enumerate(judgment["actions"], start=1):
        action_id = f"{trajectory_id}::A{index}"
        selected = item["status"] != "proposed"
        label = item["label"]
        categories[action_id] = label
        evidence = []
        observed_seconds = 0.0
        observed_found = False
        for ref in item["evidence_refs"]:
            event = event_map[ref]
            evidence.append({"source": "trajectory", "source_id": ref, "quote": event["content"][:240]})
            if selected and ref not in used_duration_events and event.get("duration_ms") is not None:
                observed_seconds += float(event["duration_ms"]) / 1000.0
                observed_found = True
                used_duration_events.add(ref)
        origin = "reference" if label == "necessary" else "agent"
        actions.append({
            "action_id": action_id,
            "task_id": task_id,
            "trajectory_id": trajectory_id,
            "description": item["description"],
            "action_type": item["action_type"],
            "status": item["status"],
            "origin": origin,
            "selected_by_agent": selected,
            "evidence": evidence,
        })
        required = 4.0 if label == "necessary" else 2.0 if label == "optional" else 0.0 if label == "avoidable" else 1.0
        impact = 2.0 if label == "necessary" else 1.0 if label == "optional" else 0.0
        estimated_machine = item["estimated_machine_minutes"] if item["estimated_machine_minutes"] is not None else 0.1
        machine_source = "observed" if observed_found else "estimated" if item["estimated_machine_minutes"] is not None else "imputed"
        observed_status = "helped" if selected and label in {"necessary", "optional"} else "no_effect" if selected and label == "avoidable" else "uncertain" if selected else "not_run"
        realized = impact if observed_status == "helped" else 0.0 if observed_status == "no_effect" else None
        substitute = None
        if item.get("cheaper_substitute"):
            substitute = {"description": item["cheaper_substitute"], "cost_fraction": 0.5, "comparable_benefit": True}
        reason = None
        if item["action_type"] == "defensive":
            justified = label == "necessary"
            reason = {
                "concrete_failure": justified,
                "supported_by_case": justified,
                "material_consequence": justified,
                "action_reduces_harm": justified,
                "no_comparable_cheaper_action": justified,
                "must_act_now": justified,
                "reason": item.get("explanation") or "Blind action judgment.",
            }
        annotations.append({
            "annotation_id": f"annotation::{action_id}",
            "annotator_id": judgment["evaluator_id"],
            "action_id": action_id,
            "problem_probability": 1.0 if label == "necessary" else 0.5 if label in {"optional", "unresolved"} else 0.25,
            "success_probability": 1.0 if observed_status == "helped" else 0.2,
            "required_for_task": required,
            "outcome_impact": impact,
            "decision_impact": impact if canonical_task["domain"] == "review" else 0.0,
            "feasibility": 1.0,
            "estimated_human_minutes": 0.0,
            "estimated_machine_minutes": float(estimated_machine),
            "actual_human_minutes": None,
            "actual_machine_minutes": observed_seconds / 60.0 if observed_found else None,
            "compute_or_money_cost": 0.0,
            "opportunity_cost": 1.0 if label == "avoidable" else 0.0,
            "user_burden": None if canonical_task["review_context"] == "external_peer" else 0.0,
            "cheaper_substitute": substitute,
            "defensive_reason": reason,
            "observed_result": {"status": observed_status, "realized_impact": realized},
            "annotator_confidence": item["confidence"],
            "evidence": evidence,
        })
        explanations[action_id] = {
            "label": label,
            "atomic": item.get("atomic"),
            "requirement_id": item.get("requirement_id"),
            "omission_consequence": item.get("omission_consequence"),
            "explanation": item.get("explanation"),
            "cheaper_substitute": item.get("cheaper_substitute"),
            "cost_source": machine_source,
            "cost_method": "visible_event_duration" if machine_source == "observed" else "llm_estimate" if machine_source == "estimated" else "default_action_prior",
            "confidence": item["confidence"],
            "evidence_refs": item["evidence_refs"],
            "evidence": evidence,
        }
    for index, item in enumerate(judgment["missed_actions"], start=1):
        action_id = f"{trajectory_id}::M{index}"
        categories[action_id] = "missed"
        quote = next((row["description"] for row in canonical_task["completion_criteria"] if row["criterion_id"] == item["requirement_id"]), canonical_task["objective"])
        evidence = [{"source": "task", "source_id": task_id, "quote": quote}]
        actions.append({
            "action_id": action_id,
            "task_id": task_id,
            "trajectory_id": trajectory_id,
            "description": item["description"],
            "action_type": "other",
            "status": "missed",
            "origin": "reference",
            "selected_by_agent": False,
            "evidence": evidence,
        })
        annotations.append({
            "annotation_id": f"annotation::{action_id}",
            "annotator_id": judgment["evaluator_id"],
            "action_id": action_id,
            "problem_probability": 1.0,
            "success_probability": 1.0,
            "required_for_task": 4.0,
            "outcome_impact": 2.0,
            "decision_impact": 2.0 if canonical_task["domain"] == "review" else 0.0,
            "feasibility": 1.0,
            "estimated_human_minutes": 0.0,
            "estimated_machine_minutes": 0.1,
            "actual_human_minutes": None,
            "actual_machine_minutes": None,
            "compute_or_money_cost": 0.0,
            "opportunity_cost": 0.0,
            "user_burden": None if canonical_task["review_context"] == "external_peer" else 0.0,
            "cheaper_substitute": None,
            "defensive_reason": None,
            "observed_result": {"status": "not_run", "realized_impact": None},
            "annotator_confidence": item["confidence"],
            "evidence": evidence,
        })
        explanations[action_id] = {
            "label": "missed",
            "requirement_id": item["requirement_id"],
            "omission_consequence": item["omission_consequence"],
            "explanation": "Required action was absent from the visible trajectory.",
            "cheaper_substitute": None,
            "cost_source": "imputed",
            "cost_method": "default_action_prior",
            "confidence": item["confidence"],
            "evidence_refs": item.get("evidence_refs", []),
            "evidence": evidence,
        }
    bundle = {"task": canonical_task, "trajectory": trajectory, "actions": actions, "annotations": annotations, "human_feedback": None}
    score = score_bundle(bundle)
    for action in score.get("actions", []):
        info = explanations.get(action["action_id"], {})
        action["machine_time_source"] = info.get("cost_source", action.get("machine_time_source", "imputed"))
        action["machine_time_method"] = info.get("cost_method", "default_action_prior")
    score["action_categories"] = categories
    score["action_explanations"] = explanations
    score["semantic_success"] = judgment["semantic_success"]
    score["judge_confidence"] = judgment["confidence"]
    score["trajectory_elapsed_seconds"] = float(packet["verified_outcome"].get("elapsed_seconds") or 0)
    score["trajectory_usage"] = packet["verified_outcome"].get("usage")
    score["changed_paths"] = packet["verified_outcome"].get("changed_paths", [])
    return score, bundle
