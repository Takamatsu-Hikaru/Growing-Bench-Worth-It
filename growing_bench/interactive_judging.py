from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import run_agent
from .judging import extract_json


JUDGMENT_SCHEMA_VERSION = "growing-bench-interaction-judgment-1.0"
PROMPT_VERSION = "growing-bench-interaction-judge-1.0"
SPAN_LABELS = {
    "decision_relevant", "brief_acknowledgement", "requested_explanation",
    "compliance_receipt", "stale_reintroduction", "unnecessary_self_report",
    "profile_adaptation", "missed_user_signal",
}
SIGNAL_STATUSES = {"honored", "partial", "ignored", "unresolved"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def build_interaction_packet(run_dir: Path) -> dict[str, Any]:
    scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    task = json.loads((run_dir / "task.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    controller = _read_jsonl(run_dir / "controller.jsonl")
    events = []
    for row in _read_jsonl(run_dir / "trajectory.jsonl"):
        content = str(row.get("content") or row.get("visible_output") or "")
        if row.get("kind") in {"user_message", "assistant_message", "diff", "file_write", "tool_call", "command_result", "test_result", "compile_result"}:
            events.append({
                "event_id": row["event_id"], "turn_index": row.get("turn_index"),
                "kind": row.get("kind"), "status": row.get("status"),
                "content": content[:12000],
            })
    return {
        "schema_version": "growing-bench-interaction-packet-1.0",
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "user_profile": scenario["user_profile"],
            "controller_turns": controller,
        },
        "task": {
            "title": task.get("title", task["task_id"]), "kind": task["kind"],
            "completion_criteria": task.get("completion_criteria", []),
        },
        "verified_outcome": {
            "status": summary.get("status"),
            "post_checks_passed": summary.get("post_checks_passed"),
            "allowed_paths_ok": summary.get("allowed_paths_ok"),
            "machine_completion_passed": summary.get("machine_completion_passed"),
            "criterion_results": summary.get("criterion_results", []),
        },
        "events": events,
    }


def interaction_judge_prompt(packet: dict[str, Any], evaluator_id: str) -> str:
    return f"""You are a condition-blind evaluator of a real multi-turn Agent workspace trajectory.

Evaluate observable interaction behavior. Do not infer feelings or user satisfaction. Do not reward brevity by itself. Information is unnecessary only when it does not help the current user goal, decision, requested explanation, or next action. A short acknowledgement of an updated instruction may be appropriate once. A retired topic becomes stale only after the controller records it as retired.

Label exact visible spans. Also evaluate every explicit target signal in controller_turns. Workspace diffs and tool events may show whether a user signal changed behavior. Do not invent actions or evidence.

Return one JSON object and no prose:
{{
  "schema_version": "{JUDGMENT_SCHEMA_VERSION}",
  "evaluator_id": "{evaluator_id}",
  "confidence": 0.0,
  "spans": [
    {{
      "span_id": "S1",
      "event_id": "visible event id",
      "quote": "exact substring from the event",
      "label": "decision_relevant",
      "topic_id": null,
      "explanation": "why the information belongs in this label",
      "confidence": 0.0
    }}
  ],
  "signals": [
    {{
      "signal_id": "move_id::target",
      "status": "honored",
      "evidence_refs": ["visible event id"],
      "explanation": "how subsequent behavior handled the signal",
      "confidence": 0.0
    }}
  ]
}}

Allowed span labels: {sorted(SPAN_LABELS)}.
Allowed signal statuses: {sorted(SIGNAL_STATUSES)}.
Every span quote must occur literally in an assistant_message event. Cover every assistant_message with at least one label, label only the smallest sufficient spans, and do not label the same text twice. Include every target signal exactly once. Evidence for a signal must come from later Agent behavior or workspace evidence, never from the user message that introduced it. If evidence cannot resolve a signal, use unresolved.

PACKET:
{json.dumps(packet, ensure_ascii=False, sort_keys=True)}
"""


def interaction_adjudication_prompt(
    packet: dict[str, Any], evaluator_a: dict[str, Any], evaluator_b: dict[str, Any], evaluator_id: str,
) -> str:
    return f"""You are the third condition-blind interaction adjudicator. Resolve two judgments using only their visible packet evidence. Preserve genuine ambiguity as unresolved. Apply the same rule: do not infer feelings, do not reward brevity by itself, and treat a topic as stale only after the controller retires it.

Return exactly the interaction judgment JSON contract with evaluator_id {evaluator_id!r}.

PACKET:
{json.dumps(packet, ensure_ascii=False, sort_keys=True)}

EVALUATOR A:
{json.dumps(evaluator_a, ensure_ascii=False, sort_keys=True)}

EVALUATOR B:
{json.dumps(evaluator_b, ensure_ascii=False, sort_keys=True)}
"""


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise ValueError(f"{label} must be between 0 and 1")
    return result


def _signal_ids(packet: dict[str, Any]) -> set[str]:
    return {
        f"{turn['move_id']}::{target}"
        for turn in packet["scenario"]["controller_turns"]
        for target in turn.get("targets", [])
    }


def validate_interaction_judgment(raw: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != JUDGMENT_SCHEMA_VERSION:
        raise ValueError("interaction judgment schema_version is invalid")
    if not isinstance(raw.get("evaluator_id"), str) or not raw["evaluator_id"]:
        raise ValueError("interaction evaluator_id is required")
    confidence = _number(raw.get("confidence"), "confidence")
    if not isinstance(raw.get("spans"), list) or not isinstance(raw.get("signals"), list):
        raise ValueError("interaction spans and signals must be arrays")
    event_map = {row["event_id"]: row for row in packet["events"]}
    assistant_event_ids = {row["event_id"] for row in packet["events"] if row.get("kind") == "assistant_message" and row.get("content")}
    signal_turns = {f"{turn['move_id']}::{target}": int(turn["turn_index"]) for turn in packet["scenario"]["controller_turns"] for target in turn.get("targets", [])}
    spans = []
    span_ids: set[str] = set()
    span_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(raw["spans"]):
        if not isinstance(item, dict):
            raise ValueError(f"spans[{index}] must be an object")
        span_id, event_id = item.get("span_id"), item.get("event_id")
        quote, label = item.get("quote"), item.get("label")
        if not isinstance(span_id, str) or not span_id or span_id in span_ids:
            raise ValueError(f"spans[{index}] has a missing or duplicate span_id")
        if event_id not in assistant_event_ids or not isinstance(quote, str) or not quote:
            raise ValueError(f"spans[{index}] must quote an assistant_message event")
        if quote not in str(event_map[event_id].get("content") or ""):
            raise ValueError(f"spans[{index}] quote is absent from its event")
        if label not in SPAN_LABELS:
            raise ValueError(f"spans[{index}] label is invalid")
        key = (event_id, quote)
        if key in span_keys:
            raise ValueError(f"spans[{index}] duplicates a visible span")
        if item.get("topic_id") is not None and not isinstance(item.get("topic_id"), str):
            raise ValueError(f"spans[{index}].topic_id must be a string or null")
        if not isinstance(item.get("explanation"), str) or not item["explanation"]:
            raise ValueError(f"spans[{index}].explanation is required")
        spans.append({**item, "confidence": _number(item.get("confidence"), f"spans[{index}].confidence")})
        span_ids.add(span_id); span_keys.add(key)
    if {row["event_id"] for row in spans} != assistant_event_ids:
        raise ValueError("interaction judgment must label every assistant_message event")
    expected_signals = _signal_ids(packet)
    signals = []
    seen_signals: set[str] = set()
    for index, item in enumerate(raw["signals"]):
        if not isinstance(item, dict):
            raise ValueError(f"signals[{index}] must be an object")
        signal_id = item.get("signal_id")
        if signal_id not in expected_signals or signal_id in seen_signals:
            raise ValueError(f"signals[{index}] has an unknown or duplicate signal_id")
        if item.get("status") not in SIGNAL_STATUSES:
            raise ValueError(f"signals[{index}].status is invalid")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not all(ref in event_map for ref in refs):
            raise ValueError(f"signals[{index}].evidence_refs are invalid")
        if item["status"] != "unresolved" and not refs:
            raise ValueError(f"signals[{index}] requires evidence")
        if any(event_map[ref].get("kind") == "user_message" or int(event_map[ref].get("turn_index") or 0) < signal_turns[signal_id] for ref in refs):
            raise ValueError(f"signals[{index}] evidence must come from subsequent Agent or workspace behavior")
        if not isinstance(item.get("explanation"), str) or not item["explanation"]:
            raise ValueError(f"signals[{index}].explanation is required")
        signals.append({**item, "confidence": _number(item.get("confidence"), f"signals[{index}].confidence")})
        seen_signals.add(signal_id)
    if seen_signals != expected_signals:
        raise ValueError("interaction judgment must cover every target signal")
    return {
        "schema_version": JUDGMENT_SCHEMA_VERSION,
        "evaluator_id": raw["evaluator_id"], "confidence": confidence,
        "spans": spans, "signals": signals,
    }


def score_interaction(packet: dict[str, Any], judgment: dict[str, Any]) -> dict[str, Any]:
    labels = {name: 0 for name in SPAN_LABELS}
    token_counts = {name: 0 for name in SPAN_LABELS}
    for span in judgment["spans"]:
        labels[span["label"]] += 1
        token_counts[span["label"]] += len(span["quote"].split())
    relevant = sum(labels[name] for name in {"decision_relevant", "brief_acknowledgement", "requested_explanation", "profile_adaptation"})
    surfaced = len(judgment["spans"])
    unnecessary = sum(labels[name] for name in {"compliance_receipt", "stale_reintroduction", "unnecessary_self_report"})
    resolved = [row for row in judgment["signals"] if row["status"] != "unresolved"]
    signal_value = {"honored": 1.0, "partial": 0.5, "ignored": 0.0}
    update_success = None if not resolved else sum(signal_value[row["status"]] for row in resolved) / len(resolved)
    controller = packet["scenario"]["controller_turns"]
    corrections = [row for row in controller if row["role"] == "correction"]
    target_counts: dict[str, int] = {}
    for row in corrections:
        for target in row.get("targets", []):
            target_counts[target] = target_counts.get(target, 0) + 1
    repeated = sum(max(0, count - 1) for count in target_counts.values())
    ignored = sum(row["status"] == "ignored" for row in judgment["signals"])
    partial = sum(row["status"] == "partial" for row in judgment["signals"])
    takeover = any(row["role"] == "takeover" for row in controller)
    scenario_pressure_points = len(corrections) + repeated + (4 if takeover else 0)
    observed_agent_burden_points = (
        2 * labels["stale_reintroduction"] + labels["compliance_receipt"]
        + labels["unnecessary_self_report"] + 2 * ignored + partial
    )
    return {
        "schema_version": "growing-bench-interaction-score-1.0",
        "scenario_id": packet["scenario"]["scenario_id"],
        "state_update_success": update_success,
        "foreground_precision": None if surfaced == 0 else relevant / surfaced,
        "unnecessary_claim_rate": None if surfaced == 0 else unnecessary / surfaced,
        "stale_narrative_events": labels["stale_reintroduction"],
        "stale_narrative_tokens": token_counts["stale_reintroduction"],
        "compliance_receipt_events": labels["compliance_receipt"],
        "unnecessary_self_report_events": labels["unnecessary_self_report"],
        "ignored_signal_count": ignored, "partial_signal_count": partial,
        "scenario_pressure": {
            "turn_count": len(controller),
            "correction_turn_count": len(corrections),
            "repeated_target_count": repeated,
            "takeover_planned": takeover,
            "pressure_points": scenario_pressure_points,
        },
        "observed_agent_burden": {
            "ignored_signal_count": ignored,
            "partial_signal_count": partial,
            "stale_narrative_events": labels["stale_reintroduction"],
            "compliance_receipt_events": labels["compliance_receipt"],
            "unnecessary_self_report_events": labels["unnecessary_self_report"],
            "burden_points": observed_agent_burden_points,
        },
        "observed_agent_burden_points": observed_agent_burden_points,
        "span_label_counts": labels, "span_token_counts": token_counts,
        "signal_status_counts": {name: sum(row["status"] == name for row in judgment["signals"]) for name in SIGNAL_STATUSES},
    }


def _run_judge(
    prompt: str, output: Path, judge: str, model: str | None, reasoning: str,
    timeout: float, command_template: str | None,
) -> dict[str, Any]:
    workspace = output / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    result = run_agent(
        judge, prompt, workspace, output / "agent", model=model,
        reasoning=reasoning, timeout=timeout, command_template=command_template,
    )
    if result["status"] != "completed":
        raise ValueError("interaction judge failed")
    return extract_json((output / "agent" / "final.md").read_text(encoding="utf-8"))


def run_interaction_judgment(
    run_dir: Path, output: Path, *, judge: str = "codex", model: str | None = None,
    reasoning: str = "high", timeout: float = 1200, command_template: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    packet = build_interaction_packet(run_dir)
    _write_json(output / "packet.json", packet)
    raw_a = _run_judge(interaction_judge_prompt(packet, "evaluator-a"), output / "evaluator-a", judge, model, reasoning, timeout, command_template)
    a = validate_interaction_judgment(raw_a, packet)
    _write_json(output / "evaluator-a.json", a)
    consensus = a
    agreement = {"mode": "single", "exact": None}
    if strict:
        raw_b = _run_judge(interaction_judge_prompt(packet, "evaluator-b"), output / "evaluator-b", judge, model, reasoning, timeout, command_template)
        b = validate_interaction_judgment(raw_b, packet)
        _write_json(output / "evaluator-b.json", b)
        comparable_a = {key: a[key] for key in ("spans", "signals")}
        comparable_b = {key: b[key] for key in ("spans", "signals")}
        exact = comparable_a == comparable_b
        agreement = {"mode": "double_with_adjudication", "exact": exact}
        if not exact:
            raw_c = _run_judge(
                interaction_adjudication_prompt(packet, a, b, "adjudicator-c"),
                output / "adjudicator-c", judge, model, reasoning, timeout, command_template,
            )
            consensus = validate_interaction_judgment(raw_c, packet)
            _write_json(output / "adjudicator-c.json", consensus)
        else:
            consensus = {**a, "evaluator_id": "exact-consensus"}
    _write_json(output / "agreement.json", agreement)
    _write_json(output / "consensus.json", consensus)
    score = score_interaction(packet, consensus)
    _write_json(output / "score.json", score)
    return {"packet": packet, "judgment": consensus, "agreement": agreement, "score": score}
