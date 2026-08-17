from __future__ import annotations

import unittest

from growing_bench.judging import JUDGMENT_SCHEMA_VERSION, validate_judgment
from growing_bench.self_test import _action_html


def packet() -> dict:
    return {
        "task": {"completion_criteria": [{"criterion_id": "C1", "description": "Verify output"}]},
        "events": [{"event_id": "e1", "kind": "assistant_message", "content": "Ran six test suites"}],
    }


def judgment(*, atomic: bool) -> dict:
    return {
        "schema_version": JUDGMENT_SCHEMA_VERSION,
        "evaluator_id": "contract-test",
        "semantic_success": 1,
        "confidence": 0.8,
        "missed_actions": [],
        "actions": [
            {
                "action_id": "A1",
                "description": "Run the focused test and five repeated full suites",
                "action_type": "verification",
                "status": "completed",
                "label": "necessary",
                "atomic": atomic,
                "requirement_id": "C1",
                "omission_consequence": "The output would remain unverified.",
                "evidence_refs": ["e1"],
                "explanation": "Composite verification action.",
                "cheaper_substitute": None,
                "estimated_machine_minutes": 12,
                "confidence": 0.8,
            }
        ],
    }


class JudgmentContractV2Tests(unittest.TestCase):
    def test_non_atomic_necessary_action_becomes_unresolved(self) -> None:
        result = validate_judgment(judgment(atomic=False), packet())
        self.assertEqual(result["actions"][0]["label"], "unresolved")
        self.assertEqual(result["actions"][0]["gate_failure"], "necessary action was not atomic")

    def test_necessary_high_cost_never_renders_as_low_value(self) -> None:
        action_id = "trajectory::A1"
        row = {
            "action_categories": {action_id: "necessary"},
            "action_explanations": {
                action_id: {
                    "label": "necessary",
                    "requirement_id": "C1",
                    "omission_consequence": "The task fails.",
                    "explanation": "Required migration.",
                    "cost_source": "estimated",
                    "confidence": 0.9,
                    "evidence": [],
                }
            },
        }
        action = {
            "action_id": action_id,
            "description": "Apply the required migration",
            "machine_minutes": 30,
            "net_action_value": -2,
        }
        rendered = _action_html(row, action)
        self.assertIn("NECESSARY · HIGH COST", rendered)
        self.assertNotIn("LOW VALUE", rendered)
        self.assertNotIn("WASTE", rendered)


if __name__ == "__main__":
    unittest.main()
