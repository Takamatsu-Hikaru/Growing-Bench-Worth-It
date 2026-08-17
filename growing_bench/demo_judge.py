from __future__ import annotations

import json
import sys
from pathlib import Path

from .judging import JUDGMENT_SCHEMA_VERSION


def _packet(text: str) -> dict:
    marker = "PACKET:\n"
    start = text.index(marker) + len(marker)
    value, _ = json.JSONDecoder().raw_decode(text[start:].lstrip())
    return value


def main() -> int:
    prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
    packet = _packet(prompt)
    criteria = [row for row in packet["task"].get("completion_criteria", []) if isinstance(row, dict)]
    criterion = criteria[0]["criterion_id"] if criteria else "C1"
    event = next((row for row in packet["events"] if row["kind"] != "user" and row.get("content")), packet["events"][-1])
    success = 1.0 if packet["verified_outcome"].get("machine_completion_passed") else 0.0
    result = {
        "schema_version": JUDGMENT_SCHEMA_VERSION,
        "evaluator_id": "offline-demo-judge",
        "semantic_success": success,
        "confidence": 0.8,
        "actions": [{
            "action_id": "A1",
            "description": "Complete and verify the requested workspace change",
            "action_type": "verification",
            "status": "completed",
            "label": "necessary",
            "atomic": True,
            "requirement_id": criterion,
            "omission_consequence": "The declared completion condition would remain unverified.",
            "evidence_refs": [event["event_id"]],
            "explanation": "The visible action directly supports an explicit completion condition.",
            "cheaper_substitute": None,
            "estimated_machine_minutes": None,
            "confidence": 0.8,
        }],
        "missed_actions": [],
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
