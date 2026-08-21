from __future__ import annotations

import json
import sys
from pathlib import Path

from .interactive_judging import JUDGMENT_SCHEMA_VERSION as INTERACTION_SCHEMA
from .judging import JUDGMENT_SCHEMA_VERSION as ACTION_SCHEMA


def _packet(text: str) -> dict:
    marker = "PACKET:\n"
    start = text.index(marker) + len(marker)
    value, _ = json.JSONDecoder().raw_decode(text[start:].lstrip())
    return value


def _interaction(packet: dict) -> dict:
    assistant = [row for row in packet["events"] if row["kind"] == "assistant_message" and row.get("content")]
    spans = [{
        "span_id": f"S{index}", "event_id": event["event_id"], "quote": event["content"],
        "label": "brief_acknowledgement" if "Understood" in event["content"] else "decision_relevant",
        "topic_id": None, "explanation": "The visible response advances or acknowledges the current request.",
        "confidence": 0.85,
    } for index, event in enumerate(assistant, start=1)]
    evidence = [assistant[-1]["event_id"]] if assistant else [packet["events"][-1]["event_id"]]
    signals = [{
        "signal_id": f"{turn['move_id']}::{target}", "status": "honored",
        "evidence_refs": evidence, "explanation": "Subsequent visible behavior follows the supplied controller move.",
        "confidence": 0.8,
    } for turn in packet["scenario"]["controller_turns"] for target in turn.get("targets", [])]
    return {"schema_version": INTERACTION_SCHEMA, "evaluator_id": "offline-universal-judge", "confidence": 0.8, "spans": spans, "signals": signals}


def _action(packet: dict) -> dict:
    criteria = [row for row in packet["task"].get("completion_criteria", []) if isinstance(row, dict)]
    criterion = criteria[0]["criterion_id"] if criteria else "C1"
    event = next((row for row in reversed(packet["events"]) if row.get("content") and row["kind"] not in {"user", "user_message"}), packet["events"][-1])
    return {
        "schema_version": ACTION_SCHEMA, "evaluator_id": "offline-universal-judge",
        "semantic_success": 1.0 if packet["verified_outcome"].get("machine_completion_passed") else 0.0,
        "confidence": 0.8,
        "actions": [{
            "action_id": "A1", "description": "Complete and verify the requested workspace change",
            "action_type": "verification", "status": "completed", "label": "necessary", "atomic": True,
            "requirement_id": criterion, "omission_consequence": "The explicit completion condition would remain unverified.",
            "evidence_refs": [event["event_id"]], "explanation": "The visible action directly supports an explicit completion condition.",
            "cheaper_substitute": None, "estimated_machine_minutes": None, "confidence": 0.8,
        }], "missed_actions": [],
    }


def main() -> int:
    prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
    packet = _packet(prompt)
    value = _interaction(packet) if "controller_turns" in prompt or "interaction-judgment" in prompt else _action(packet)
    print(json.dumps({"final": json.dumps(value, ensure_ascii=False)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
