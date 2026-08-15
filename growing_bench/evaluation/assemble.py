#!/usr/bin/env python3
"""Materialize a canonical action-value bundle without inferred defaults.

The module joins already-validated extraction, frozen action labels, criterion
outcomes, and optional participant feedback. It does not run an evaluator or
silently promote unresolved consensus.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


BASE_DIMENSIONS = {
    "requested_by_user",
    "required_for_task",
    "problem_probability",
    "success_probability",
    "outcome_impact",
    "decision_impact",
    "time_cost",
    "feasibility",
    "opportunity_cost",
    "cheaper_substitute",
    "observed_result",
}


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected non-empty string")
    return value.strip()


def materialize_agent_actions(
    extraction_item: dict[str, Any], extraction_packet: dict[str, Any]
) -> list[dict[str, Any]]:
    """Convert one validated extractor row to canonical selected actions.

    Evidence is checked again here so callers cannot bypass the extractor's
    validation by calling the assembly layer directly.
    """

    if extraction_item.get("item_id") != extraction_packet.get("item_id"):
        raise ValueError("extraction item does not match packet")
    task = extraction_packet.get("task")
    if not isinstance(task, dict):
        raise ValueError("extraction packet task is required")
    task_id = _nonempty(task.get("task_id"), "task_id")
    trajectory_id = _nonempty(extraction_packet.get("trajectory_id"), "trajectory_id")
    event_map = {
        event.get("event_id"): event
        for event in extraction_packet.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
    }
    raw_actions = extraction_item.get("actions")
    if not isinstance(raw_actions, list):
        raise ValueError("extraction actions must be an array")
    actions = []
    seen = set()
    for index, raw in enumerate(raw_actions):
        if not isinstance(raw, dict):
            raise ValueError(f"extraction action {index} must be an object")
        local_id = _nonempty(raw.get("action_id"), f"actions[{index}].action_id")
        action_id = f"{trajectory_id}::{local_id}"
        if action_id in seen:
            raise ValueError(f"duplicate extracted action {local_id!r}")
        seen.add(action_id)
        event_id = _nonempty(raw.get("event_id"), f"actions[{index}].event_id")
        event = event_map.get(event_id)
        if not isinstance(event, dict) or event.get("kind") not in {
            "assistant", "tool_call", "tool_result", "artifact"
        }:
            raise ValueError(f"{local_id}: action evidence is not from the agent")
        quote = _nonempty(raw.get("evidence_quote"), f"actions[{index}].evidence_quote")
        if quote not in str(event.get("content", "")):
            raise ValueError(f"{local_id}: evidence quote is absent from event")
        action_type = raw.get("action_type")
        status = raw.get("status")
        if action_type not in {
            "experiment", "analysis", "edit", "implementation", "verification", "decision",
            "abstraction", "dependency", "defensive", "communication", "refusal", "other",
        }:
            raise ValueError(f"{local_id}: invalid action_type")
        if status not in {"proposed", "started", "completed", "failed", "deferred", "refused", "reverted"}:
            raise ValueError(f"{local_id}: invalid status")
        actions.append(
            {
                "action_id": action_id,
                "task_id": task_id,
                "trajectory_id": trajectory_id,
                "description": _nonempty(raw.get("description"), f"actions[{index}].description"),
                "action_type": action_type,
                "origin": "agent",
                "selected_by_agent": True,
                "status": status,
                "evidence": [{"source": "trajectory", "source_id": event_id, "quote": quote}],
            }
        )
    return actions


def apply_reference_plan(
    agent_actions: list[dict[str, Any]], reference_plan: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mark matched agent actions as reference, and add explicitly missed ones.

    A reference row must either name ``matched_action_id`` or provide every
    field needed for a missed canonical action.  No semantic matching occurs.
    """

    actions = [dict(action) for action in agent_actions]
    by_id = {action.get("action_id"): action for action in actions}
    if None in by_id or len(by_id) != len(actions):
        raise ValueError("agent action ids are missing or duplicated")
    seen_matches = set()
    for index, reference in enumerate(reference_plan):
        if not isinstance(reference, dict):
            raise ValueError(f"reference_plan[{index}] must be an object")
        matched = reference.get("matched_action_id")
        if matched is not None:
            if set(reference) != {"reference_id", "matched_action_id"}:
                raise ValueError("matched reference may only contain reference_id and matched_action_id")
            _nonempty(reference.get("reference_id"), f"reference_plan[{index}].reference_id")
            if matched not in by_id or matched in seen_matches:
                raise ValueError("matched reference points to an unknown or repeated action")
            seen_matches.add(matched)
            by_id[matched]["origin"] = "reference"
            continue
        required = {
            "reference_id", "task_id", "trajectory_id", "description", "action_type", "evidence"
        }
        if set(reference) != required:
            raise ValueError(f"unmatched reference fields must be exactly {sorted(required)}")
        reference_id = _nonempty(reference["reference_id"], f"reference_plan[{index}].reference_id")
        action_id = f"reference::{reference_id}"
        if action_id in by_id:
            raise ValueError(f"duplicate reference action {reference_id!r}")
        action = {
            "action_id": action_id,
            "task_id": _nonempty(reference["task_id"], "reference task_id"),
            "trajectory_id": _nonempty(reference["trajectory_id"], "reference trajectory_id"),
            "description": _nonempty(reference["description"], "reference description"),
            "action_type": reference["action_type"],
            "origin": "reference",
            "selected_by_agent": False,
            "status": "missed",
            "evidence": reference["evidence"],
        }
        actions.append(action)
        by_id[action_id] = action
    return actions


def _canonical_evidence(
    citations: Iterable[dict[str, str]], packet: dict[str, Any], action: dict[str, Any],
    task: dict[str, Any], trajectory: dict[str, Any]
) -> list[dict[str, str]]:
    event_ids = [event["event_id"] for event in trajectory["events"]]
    result: list[dict[str, str]] = []
    seen = set()
    for citation in citations:
        source_ref, quote = citation["source_ref"], citation["quote"]
        if source_ref == "action:description":
            candidates = [{"source": "action", "source_id": action["action_id"], "quote": quote}]
        elif source_ref.startswith("event:"):
            try:
                event_id = event_ids[int(source_ref.split(":", 1)[1]) - 1]
            except (ValueError, IndexError):
                raise ValueError(f"invalid event source ref {source_ref!r}") from None
            candidates = [{"source": "trajectory", "source_id": event_id, "quote": quote}]
        elif source_ref.startswith("task:"):
            candidates = [{"source": "task", "source_id": task["task_id"], "quote": quote}]
        else:
            raise ValueError(f"unsupported gold evidence source {source_ref!r}")
        for candidate in candidates:
            key = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(candidate)
    if not result:
        raise ValueError("annotation evidence cannot be empty")
    return result


def assemble_annotations(
    task: dict[str, Any], trajectory: dict[str, Any], actions: list[dict[str, Any]],
    validated_gold: dict[str, Any], packets: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join approved per-dimension gold into one canonical annotation/action."""

    action_map = {action["action_id"]: action for action in actions}
    if len(action_map) != len(actions) or not actions:
        raise ValueError("actions must be non-empty with unique ids")
    packet_map = {packet["packet_id"]: packet for packet in packets}
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for item in validated_gold.get("items", []):
        if item.get("status") != "approved":
            raise ValueError("every required annotation dimension needs approved human gold")
        action_id, dimension = item.get("action_id"), item.get("dimension")
        packet = packet_map.get(item.get("packet_id"))
        if action_id not in action_map or packet is None:
            raise ValueError("gold item has invalid action or packet linkage")
        packet_action_ref = packet.get("action", {}).get("action_ref")
        if packet.get("dimension") != dimension:
            raise ValueError("gold item dimension does not match bound packet")
        peer_packets = [
            candidate for candidate in packet_map.values()
            if candidate.get("action", {}).get("action_ref") == packet_action_ref
        ]
        bound_action_ids = {
            peer.get("action_id") for peer in validated_gold.get("items", [])
            if peer.get("packet_id") in {candidate.get("packet_id") for candidate in peer_packets}
        }
        if bound_action_ids != {action_id}:
            raise ValueError("gold item action does not match bound packet")
        dimensions = grouped.setdefault(action_id, {})
        if dimension in dimensions:
            raise ValueError("duplicate action/dimension gold")
        dimensions[dimension] = item
    annotations = []
    ux = task.get("user_experience_applicable") is True
    for action_id in sorted(action_map):
        action = action_map[action_id]
        expected = set(BASE_DIMENSIONS)
        if ux:
            expected.add("user_burden")
        if action.get("action_type") == "defensive":
            expected.add("defensive_reason")
        dimensions = grouped.get(action_id, {})
        if set(dimensions) != expected:
            raise ValueError(
                f"{action_id}: annotation dimensions incomplete; "
                f"missing={sorted(expected - set(dimensions))} extra={sorted(set(dimensions) - expected)}"
            )
        answer = {name: dimensions[name]["gold_answer"] for name in expected}
        time = answer["time_cost"]
        substitute = answer["cheaper_substitute"]
        canonical_substitute = None if not substitute["exists"] else {
            "description": substitute["description"],
            "comparable_benefit": substitute["comparable_benefit"],
            "cost_fraction": substitute["cost_fraction"],
        }
        citations = []
        adjudicators = set()
        confidences = []
        for item in dimensions.values():
            citations.extend(item["gold_evidence"])
            adjudicators.add(item["adjudicator_id"])
            confidences.append(float(item["gold_confidence"]))
        reference_type = str(validated_gold.get("reference_type", "human_gold"))
        identity_prefix = "ai-consensus:" if reference_type.startswith("ai_") else "human-gold:"
        identity = identity_prefix + hashlib.sha256(
            "|".join(sorted(adjudicators)).encode("utf-8")
        ).hexdigest()[:12]
        annotations.append(
            {
                "annotation_id": f"annotation::{action_id}",
                "action_id": action_id,
                "annotator_id": identity,
                "requested_by_user": answer["requested_by_user"]["value"],
                "required_for_task": answer["required_for_task"]["value"],
                "problem_probability": answer["problem_probability"]["value"],
                "success_probability": answer["success_probability"]["value"],
                "outcome_impact": answer["outcome_impact"]["value"],
                "decision_impact": answer["decision_impact"]["value"],
                **time,
                "feasibility": answer["feasibility"]["value"],
                "opportunity_cost": answer["opportunity_cost"]["value"],
                "user_burden": answer["user_burden"]["value"] if ux else None,
                "cheaper_substitute": canonical_substitute,
                "observed_result": answer["observed_result"],
                "defensive_reason": answer.get("defensive_reason"),
                # Conservative aggregation: the weakest approved dimension is
                # the confidence of the composite record.
                "annotator_confidence": min(confidences),
                "evidence": _canonical_evidence(citations, packet_map[next(iter(dimensions.values()))["packet_id"]], action, task, trajectory),
            }
        )
    return annotations


def assemble_bundle(
    task: dict[str, Any], trajectory: dict[str, Any], actions: list[dict[str, Any]],
    validated_gold: dict[str, Any], packets: Iterable[dict[str, Any]],
    human_feedback: dict[str, Any] | None
) -> dict[str, Any]:
    external = task.get("domain") == "external_peer_review" or task.get("review_context") in {
        "external_peer", "external_peer_review"
    }
    if external and human_feedback is not None:
        raise ValueError("human feedback / user experience is not applicable to external peer review")
    return {
        "task": task,
        "trajectory": trajectory,
        "actions": actions,
        "annotations": assemble_annotations(task, trajectory, actions, validated_gold, packets),
        "human_feedback": human_feedback,
    }
