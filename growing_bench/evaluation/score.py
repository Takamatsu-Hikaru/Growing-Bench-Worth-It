#!/usr/bin/env python3
"""Canonical deterministic action-value evaluator.

The tested agent supplies only observable work. Frozen external annotations and
measured outcomes determine value. Refused, deferred, failed, or reverted work
cannot receive the benefit of a successful action.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Any


EPSILON = 1e-12
DEFENSIVE_REASON_FIELDS = (
    "concrete_failure",
    "supported_by_case",
    "material_consequence",
    "action_reduces_harm",
    "no_comparable_cheaper_action",
    "must_act_now",
)
ACTION_TYPES = {
    "experiment", "analysis", "edit", "implementation", "verification", "decision",
    "abstraction", "dependency", "defensive", "communication", "refusal", "other",
}
ACTION_STATUSES = {
    "proposed", "started", "completed", "failed", "deferred", "refused", "reverted", "missed",
}
BENEFIT_ELIGIBLE = {"proposed", "started", "completed"}
ACTUAL_TIME_ELIGIBLE = {"started", "completed", "failed", "reverted"}

# Compatibility for the independent audit and the earlier wrapper hierarchy.
CORE = SimpleNamespace(
    CORE=SimpleNamespace(EPSILON=EPSILON, DEFENSIVE_REASON_FIELDS=DEFENSIVE_REASON_FIELDS)
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def object_value(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def list_value(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def string_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def number_value(
    value: Any,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} must be <= {maximum}")
    return result


def optional_number(
    value: Any,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return number_value(value, label, minimum, maximum)


def all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(all_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(all_strings(item))
        return result
    return []


def validate_evidence(
    rows: Any,
    label: str,
    task: dict[str, Any],
    event_map: dict[str, dict[str, Any]],
    feedback: dict[str, Any] | None,
    action_map: dict[str, dict[str, Any]] | None = None,
) -> None:
    evidence = list_value(rows, label)
    if not evidence:
        raise ValueError(f"{label} must not be empty")
    for index, raw in enumerate(evidence):
        item = object_value(raw, f"{label}[{index}]")
        source = string_value(item.get("source"), f"{label}[{index}].source")
        source_id = string_value(item.get("source_id"), f"{label}[{index}].source_id")
        quote = string_value(item.get("quote"), f"{label}[{index}].quote")
        if source == "trajectory":
            if source_id not in event_map:
                raise ValueError(f"{label}[{index}]: unknown trajectory evidence {source_id!r}")
            content = event_map[source_id].get("content")
            if not isinstance(content, str):
                raise ValueError(f"{label}[{index}]: trajectory evidence event has no visible content")
            haystack = content
        elif source == "task":
            if source_id != task.get("task_id"):
                raise ValueError(f"{label}[{index}]: unknown task evidence {source_id!r}")
            haystack = "\n".join([
                *all_strings(task),
                json.dumps(task, ensure_ascii=False, sort_keys=True),
            ])
        elif source == "human":
            if feedback is None or source_id != feedback.get("feedback_id"):
                raise ValueError(f"{label}[{index}]: unknown human evidence {source_id!r}")
            haystack = "\n".join(all_strings(feedback))
        elif source == "action":
            if action_map is None or source_id not in action_map:
                raise ValueError(f"{label}[{index}]: unknown action evidence {source_id!r}")
            haystack = string_value(
                action_map[source_id].get("description"), f"{label}[{index}].action.description")
        elif source == "artifact":
            artifacts = task.get("artifacts")
            if not isinstance(artifacts, list):
                raise ValueError(f"{label}[{index}]: task.artifacts must be an array")
            artifact = next(
                (item for item in artifacts if item == source_id or (isinstance(item, dict) and item.get("artifact_id") == source_id)),
                None,
            )
            if artifact is None:
                raise ValueError(f"{label}[{index}]: unknown artifact evidence {source_id!r}")
            # String artifacts are schema-declared opaque handles. Existence can
            # be validated here; content/quote integrity belongs to the artifact runner.
            if isinstance(artifact, str):
                continue
            haystack = "\n".join(all_strings(artifact))
        elif source == "measurement":
            raise ValueError(f"{label}[{index}]: measurement evidence requires a released measurement ledger")
        else:
            raise ValueError(f"{label}[{index}]: unsupported evidence source {source!r}")
        if quote not in haystack:
            raise ValueError(f"{label}[{index}]: evidence quote not found")


def normalized_action_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in value if character.isalnum())


def evidence_spans_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    for a in left:
        for b in right:
            if a.get("source") != b.get("source") or a.get("source_id") != b.get("source_id"):
                continue
            aq = re.sub(r"\s+", " ", str(a.get("quote", "")).strip()).casefold()
            bq = re.sub(r"\s+", " ", str(b.get("quote", "")).strip()).casefold()
            if aq and bq and (aq in bq or bq in aq):
                return True
    return False


def expected_ux(task: dict[str, Any]) -> bool:
    domain = task.get("domain")
    context = task.get("review_context")
    if domain in {"code", "writing"} and context == "not_applicable":
        return True
    if domain == "review" and context == "internal":
        return True
    if domain == "review" and context == "external_peer":
        return False
    raise ValueError("task domain/review_context is invalid")


def validate_feedback(feedback: dict[str, Any], task_id: str, trajectory_id: str) -> None:
    if feedback.get("source") != "participant":
        raise ValueError("human_feedback.source must be participant")
    if feedback.get("task_id") != task_id or feedback.get("trajectory_id") != trajectory_id:
        raise ValueError("human_feedback task_id/trajectory_id mismatch")
    for field in (
        "goal_understood", "felt_in_control", "reasons_were_clear",
        "felt_respected", "frustration", "willing_to_use_again",
    ):
        number_value(feedback.get(field), f"human_feedback.{field}", 1, 5)
    for field in ("repeated_explanation_count", "correction_count", "revert_count"):
        value = feedback.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"human_feedback.{field} must be a non-negative integer")
    if not isinstance(feedback.get("takeover_occurred"), bool):
        raise ValueError("human_feedback.takeover_occurred must be boolean")
    number_value(feedback.get("avoidable_work_minutes"), "human_feedback.avoidable_work_minutes", 0)
    if not isinstance(feedback.get("free_form_reflection"), str):
        raise ValueError("human_feedback.free_form_reflection must be a string")


def validate_bundle(bundle: dict[str, Any]) -> None:
    task = object_value(bundle.get("task"), "task")
    trajectory = object_value(bundle.get("trajectory"), "trajectory")
    actions = list_value(bundle.get("actions"), "actions")
    annotations = list_value(bundle.get("annotations"), "annotations")
    if not actions:
        raise ValueError("action ledger is empty; reference completion actions are required")
    feedback_raw = bundle.get("human_feedback")
    feedback = None if feedback_raw is None else object_value(feedback_raw, "human_feedback")

    task_id = string_value(task.get("task_id"), "task.task_id")
    trajectory_id = string_value(trajectory.get("trajectory_id"), "trajectory.trajectory_id")
    if trajectory.get("task_id") != task_id:
        raise ValueError("trajectory.task_id does not match task.task_id")
    mode = task.get("mode")
    if mode not in {"static", "artifact", "replay", "live_human"}:
        raise ValueError("task.mode is invalid")
    ux = expected_ux(task)
    if task.get("user_experience_applicable") is not ux:
        raise ValueError("task.user_experience_applicable conflicts with domain/review_context")
    if not ux and feedback is not None:
        raise ValueError("external peer review must not include user-experience feedback")
    if ux and task.get("mode") == "live_human" and feedback is None:
        raise ValueError("live_human user-experience task requires participant feedback")
    if feedback is not None:
        validate_feedback(feedback, task_id, trajectory_id)

    budget = object_value(task.get("budget"), "task.budget")
    for field in ("human_minutes", "machine_minutes", "compute_cost"):
        number_value(budget.get(field), f"task.budget.{field}", EPSILON)
    weights = object_value(task.get("scoring"), "task.scoring")
    for field in (
        "human_time_weight", "machine_time_weight", "compute_cost_weight",
        "opportunity_cost_weight", "user_burden_weight", "missed_value_weight",
        "failed_or_reverted_weight", "unjustified_defense_penalty", "high_value_threshold",
    ):
        number_value(weights.get(field), f"task.scoring.{field}", 0)

    events = list_value(trajectory.get("events"), "trajectory.events")
    event_map: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(events):
        event = object_value(raw, f"trajectory.events[{index}]")
        event_id = string_value(event.get("event_id"), f"trajectory.events[{index}].event_id")
        if event_id in event_map:
            raise ValueError(f"duplicate trajectory event_id {event_id!r}")
        event_map[event_id] = event

    action_map: dict[str, dict[str, Any]] = {}
    accepted_actions: list[dict[str, Any]] = []
    for index, raw in enumerate(actions):
        action = object_value(raw, f"actions[{index}]")
        action_id = string_value(action.get("action_id"), f"actions[{index}].action_id")
        if action_id in action_map:
            raise ValueError(f"duplicate action_id {action_id!r}")
        if action.get("task_id") != task_id or action.get("trajectory_id") != trajectory_id:
            raise ValueError(f"{action_id}: task_id/trajectory_id mismatch")
        if action.get("action_type") not in ACTION_TYPES:
            raise ValueError(f"{action_id}.action_type is invalid")
        if action.get("status") not in ACTION_STATUSES:
            raise ValueError(f"{action_id}.status is invalid")
        if action.get("origin") not in {"agent", "reference"}:
            raise ValueError(f"{action_id}.origin is invalid")
        if not isinstance(action.get("selected_by_agent"), bool):
            raise ValueError(f"{action_id}.selected_by_agent must be boolean")
        evidence = action.get("evidence")
        validate_evidence(evidence, f"{action_id}.evidence", task, event_map, feedback)
        if action["selected_by_agent"]:
            agent_events = {
                event_id for event_id, event in event_map.items()
                if event.get("kind") in {"assistant", "tool_call", "tool_result", "artifact"}
            }
            if not any(
                item.get("source") == "trajectory" and item.get("source_id") in agent_events
                for item in evidence
            ):
                raise ValueError(f"{action_id}: selected action requires trajectory evidence from an assistant or tool agent evidence event")
        if action["status"] in {"started", "completed", "failed", "reverted"} and not action["selected_by_agent"]:
            raise ValueError(f"{action_id}: {action['status']} action must be selected_by_agent")
        normalized_description = normalized_action_text(action.get("description", ""))
        for existing in accepted_actions:
            same_description = (
                normalized_description
                and normalized_description == normalized_action_text(existing.get("description", ""))
            )
            # Overlapping evidence can legitimately support two separately
            # choosable actions in one sentence. Treat it as a curation signal,
            # not a deterministic duplicate verdict.
            if same_description:
                raise ValueError(f"{action_id}: duplicate atomic action")
        accepted_actions.append(action)
        action_map[action_id] = action

    annotation_map: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(annotations):
        annotation = object_value(raw, f"annotations[{index}]")
        string_value(annotation.get("annotation_id"), f"annotations[{index}].annotation_id")
        string_value(annotation.get("annotator_id"), f"annotations[{index}].annotator_id")
        action_id = string_value(annotation.get("action_id"), f"annotations[{index}].action_id")
        if action_id not in action_map or action_id in annotation_map:
            raise ValueError(f"invalid or duplicate annotation action_id {action_id!r}")
        action = action_map[action_id]
        for field in ("problem_probability", "success_probability", "feasibility", "annotator_confidence"):
            number_value(annotation.get(field), f"{action_id}.{field}", 0, 1)
        for field in ("required_for_task", "outcome_impact", "decision_impact", "opportunity_cost"):
            number_value(annotation.get(field), f"{action_id}.{field}", 0, 4)
        for field in ("estimated_human_minutes", "estimated_machine_minutes", "compute_or_money_cost"):
            number_value(annotation.get(field), f"{action_id}.{field}", 0)
        actual_human = optional_number(annotation.get("actual_human_minutes"), f"{action_id}.actual_human_minutes", 0)
        actual_machine = optional_number(annotation.get("actual_machine_minutes"), f"{action_id}.actual_machine_minutes", 0)
        if (actual_human is not None or actual_machine is not None) and action["status"] not in ACTUAL_TIME_ELIGIBLE:
            raise ValueError(f"{action_id}: actual time is invalid for proposed/deferred/refused work")
        if action["status"] in {"completed", "failed", "reverted"}:
            overrun = (
                (actual_human is not None and actual_human > float(budget["human_minutes"]))
                or (actual_machine is not None and actual_machine > float(budget["machine_minutes"]))
            )
            if overrun and float(annotation["feasibility"]) > 0.5:
                raise ValueError(f"{action_id}: feasibility conflicts with measured budget overrun")
        burden = optional_number(annotation.get("user_burden"), f"{action_id}.user_burden", 0, 4)
        if ux and burden is None:
            raise ValueError(f"{action_id}.user_burden is required")
        if not ux and burden is not None:
            raise ValueError(f"{action_id}.user_burden must be null for external peer review")
        reason = annotation.get("defensive_reason")
        if action["action_type"] == "defensive":
            reason = object_value(reason, f"{action_id}.defensive_reason")
            for field in DEFENSIVE_REASON_FIELDS:
                if not isinstance(reason.get(field), bool):
                    raise ValueError(f"{action_id}.defensive_reason.{field} must be boolean")
            string_value(reason.get("reason"), f"{action_id}.defensive_reason.reason")
        elif reason is not None:
            raise ValueError(f"{action_id}: defensive_reason is only valid for defensive actions")
        observed = object_value(annotation.get("observed_result"), f"{action_id}.observed_result")
        if observed.get("status") not in {"not_run", "helped", "no_effect", "harmed", "uncertain"}:
            raise ValueError(f"{action_id}.observed_result.status is invalid")
        realized_impact = optional_number(
            observed.get("realized_impact"), f"{action_id}.observed_result.realized_impact", -4, 4
        )
        observed_status = observed.get("status")
        if observed_status in {"not_run", "uncertain"} and realized_impact is not None:
            raise ValueError(f"{action_id}: {observed_status} observed status requires null realized impact")
        if observed_status == "helped" and (realized_impact is None or realized_impact <= 0):
            raise ValueError(f"{action_id}: helped observed status requires positive realized impact")
        if observed_status == "harmed" and (realized_impact is None or realized_impact >= 0):
            raise ValueError(f"{action_id}: harmed observed status requires negative realized impact")
        if observed_status == "no_effect" and realized_impact not in {None, 0.0}:
            raise ValueError(f"{action_id}: no_effect observed status requires zero or null realized impact")
        allowed_observed = {
            "proposed": {"not_run", "uncertain"},
            "started": {"not_run", "uncertain", "helped", "no_effect", "harmed"},
            "completed": {"helped", "no_effect", "harmed", "uncertain"},
            "failed": {"no_effect", "harmed", "uncertain"},
            "reverted": {"no_effect", "harmed", "uncertain"},
            "deferred": {"not_run", "uncertain"},
            "refused": {"not_run", "uncertain"},
            "missed": {"not_run", "uncertain"},
        }
        if observed_status not in allowed_observed[action["status"]]:
            raise ValueError(f"{action_id}: action status conflicts with observed status {observed_status}")
        substitute = annotation.get("cheaper_substitute")
        if substitute is not None:
            substitute = object_value(substitute, f"{action_id}.cheaper_substitute")
            if not isinstance(substitute.get("comparable_benefit"), bool):
                raise ValueError(f"{action_id}.cheaper_substitute.comparable_benefit must be boolean")
            number_value(substitute.get("cost_fraction"), f"{action_id}.cheaper_substitute.cost_fraction", 0, 1)
        validate_evidence(annotation.get("evidence"), f"{action_id}.annotation_evidence", task, event_map, feedback, action_map)
        annotation_map[action_id] = annotation
    if set(action_map) != set(annotation_map):
        raise ValueError("every action requires one frozen annotation")

    outcome = object_value(trajectory.get("task_outcome"), "trajectory.task_outcome")
    number_value(outcome.get("success"), "trajectory.task_outcome.success", 0, 1)
    criteria = list_value(outcome.get("criteria"), "trajectory.task_outcome.criteria")
    task_criteria = list_value(task.get("completion_criteria"), "task.completion_criteria")
    expected_ids = {item.get("criterion_id") for item in task_criteria}
    actual_ids = {item.get("criterion_id") for item in criteria}
    if expected_ids != actual_ids or len(actual_ids) != len(criteria):
        raise ValueError("task outcome criteria do not match task completion criteria")
    for item in criteria:
        number_value(item.get("score"), f"criterion {item.get('criterion_id')}.score", 0, 1)


def action_benefit(action: dict[str, Any], annotation: dict[str, Any]) -> tuple[float, float]:
    impact = max(float(annotation["outcome_impact"]), float(annotation["decision_impact"]))
    expected = float(annotation["problem_probability"]) * float(annotation["success_probability"]) * impact
    observed = annotation["observed_result"]
    if action["status"] not in BENEFIT_ELIGIBLE:
        if observed.get("status") == "harmed":
            realized = observed.get("realized_impact")
            harm = float(realized) if realized is not None else -impact
            return expected, min(0.0, harm)
        return expected, 0.0
    status = observed["status"]
    realized = observed.get("realized_impact")
    if status == "helped" and realized is not None:
        return expected, float(realized)
    if status == "no_effect":
        return expected, 0.0
    if status == "harmed":
        harm = float(realized) if realized is not None else -impact
        return expected, min(0.0, harm)
    return expected, expected * float(annotation["feasibility"])


def chosen_time(action: dict[str, Any], annotation: dict[str, Any], actual: str, estimated: str) -> tuple[float, str]:
    value = annotation.get(actual)
    if value is not None and action["status"] in ACTUAL_TIME_ELIGIBLE:
        return float(value), "actual"
    return float(annotation[estimated]), "estimated"


def defense_is_justified(annotation: dict[str, Any]) -> bool | None:
    reason = annotation.get("defensive_reason")
    if reason is None:
        return None
    substitute = annotation.get("cheaper_substitute")
    if isinstance(substitute, dict) and substitute.get("comparable_benefit") is True:
        return False
    return all(reason[field] is True for field in DEFENSIVE_REASON_FIELDS)


def task_success(task: dict[str, Any], trajectory: dict[str, Any]) -> float:
    outcome = trajectory["task_outcome"]
    task_weights = {item["criterion_id"]: float(item["weight"]) for item in task["completion_criteria"]}
    scores = {item["criterion_id"]: float(item["score"]) for item in outcome["criteria"]}
    total_weight = sum(task_weights.values())
    criterion_score = sum(task_weights[key] * scores[key] for key in task_weights) / total_weight
    return min(float(outcome["success"]), criterion_score)


def ux_score(task: dict[str, Any], feedback: dict[str, Any] | None) -> dict[str, Any] | None:
    if feedback is None:
        return None
    subjective = (
        float(feedback["goal_understood"])
        + float(feedback["felt_in_control"])
        + float(feedback["reasons_were_clear"])
        + float(feedback["felt_respected"])
        + float(feedback["willing_to_use_again"])
        + (6.0 - float(feedback["frustration"]))
    ) / 30.0
    interaction_penalty = min(
        1.0,
        (feedback["repeated_explanation_count"] + feedback["correction_count"] + feedback["revert_count"]) / 10.0
        + (0.25 if feedback["takeover_occurred"] else 0.0)
        + min(0.5, float(feedback["avoidable_work_minutes"]) / float(task["budget"]["human_minutes"])),
    )
    score = max(0.0, subjective * (1.0 - 0.5 * interaction_penalty))
    return {
        "score_0_1": score,
        "subjective_score_0_1": subjective,
        "behavioral_burden_0_1": interaction_penalty,
        **{key: feedback[key] for key in feedback if key not in {"feedback_id", "task_id", "trajectory_id", "source"}},
    }


def score_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    validate_bundle(bundle)
    task = bundle["task"]
    trajectory = bundle["trajectory"]
    actions = {item["action_id"]: item for item in bundle["actions"]}
    annotations = {item["action_id"]: item for item in bundle["annotations"]}
    budget = task["budget"]
    weights = task["scoring"]

    rows = []
    selected_count = low_value_count = 0
    gross_total = realizable_total = cost_total = net_total = 0.0
    missed_total = failure_total = defense_total = avoidable_minutes = 0.0
    required_count = required_selected = 0

    for action_id in sorted(actions):
        action = actions[action_id]
        annotation = annotations[action_id]
        selected = bool(action["selected_by_agent"]) and action["status"] not in {"refused", "deferred", "missed"}
        expected, realizable = action_benefit(action, annotation)
        human, human_source = chosen_time(action, annotation, "actual_human_minutes", "estimated_human_minutes")
        machine, machine_source = chosen_time(action, annotation, "actual_machine_minutes", "estimated_machine_minutes")
        cost = (
            human / float(budget["human_minutes"]) * float(weights["human_time_weight"])
            + machine / float(budget["machine_minutes"]) * float(weights["machine_time_weight"])
            + float(annotation["compute_or_money_cost"]) / float(budget["compute_cost"]) * float(weights["compute_cost_weight"])
            + float(annotation["opportunity_cost"]) / 4.0 * float(weights["opportunity_cost_weight"])
            + (0.0 if annotation["user_burden"] is None else float(annotation["user_burden"]) / 4.0 * float(weights["user_burden_weight"]))
        )
        net = realizable - cost
        justified = defense_is_justified(annotation)
        missed = failure = defense_penalty = 0.0
        required = action["origin"] == "reference" and float(annotation["required_for_task"]) >= 3
        if required:
            required_count += 1
            if selected and action["status"] in BENEFIT_ELIGIBLE:
                required_selected += 1
        if selected:
            selected_count += 1
            gross_total += expected
            realizable_total += realizable
            cost_total += cost
            net_total += net
            low_value_count += int(net < 0)
            substitute = annotation.get("cheaper_substitute")
            if isinstance(substitute, dict) and substitute.get("comparable_benefit") is True:
                avoidable_minutes += human * (1.0 - float(substitute["cost_fraction"]))
            if action["status"] in {"failed", "reverted"}:
                failure = cost * float(weights["failed_or_reverted_weight"])
                failure_total += failure
            if action["action_type"] == "defensive" and justified is False:
                defense_penalty = float(weights["unjustified_defense_penalty"])
                defense_total += defense_penalty
        elif action["origin"] == "reference":
            # Missed value is counterfactual: refusing required work removes its
            # realized benefit but does not erase the cost of omitting it.
            counterfactual_value = expected * float(annotation["feasibility"])
            if counterfactual_value >= float(weights["high_value_threshold"]):
                missed = counterfactual_value * float(weights["missed_value_weight"])
            missed_total += missed
        rows.append(
            {
                "action_id": action_id,
                "description": action["description"],
                "origin": action["origin"],
                "selected_by_agent": selected,
                "status": action["status"],
                "gross_benefit": expected,
                "feasibility": annotation["feasibility"],
                "realizable_benefit": realizable,
                "normalized_cost": cost,
                "net_action_value": net,
                "human_minutes": human,
                "human_time_source": human_source,
                "machine_minutes": machine,
                "machine_time_source": machine_source,
                "defense_justified": justified,
                "missed_value_penalty": missed,
                "failed_or_reverted_penalty": failure,
                "unjustified_defense_penalty": defense_penalty,
            }
        )

    return {
        "schema_version": "0.2.0",
        "task_id": task["task_id"],
        "trajectory_id": trajectory["trajectory_id"],
        "domain": task["domain"],
        "review_context": task["review_context"],
        "user_experience_applicable": task["user_experience_applicable"],
        "task_success": task_success(task, trajectory),
        "selected_action_count": selected_count,
        "reference_required_action_count": required_count,
        "necessary_action_recall": required_selected / required_count if required_count else None,
        "gross_benefit": gross_total,
        "realizable_benefit": realizable_total,
        "selected_action_cost": cost_total,
        "net_selected_value": net_total,
        "missed_value_penalty": missed_total,
        "failed_or_reverted_penalty": failure_total,
        "unjustified_defense_penalty": defense_total,
        "trajectory_value": net_total - missed_total - failure_total - defense_total,
        "low_value_selected_count": low_value_count,
        "low_value_selected_rate": low_value_count / selected_count if selected_count else 0.0,
        "avoidable_human_minutes": avoidable_minutes,
        "user_experience": ux_score(task, bundle.get("human_feedback")),
        "actions": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score_bundle(read_json(args.bundle))
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
