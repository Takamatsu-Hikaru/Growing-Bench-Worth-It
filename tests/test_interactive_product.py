from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from growing_bench.interactive import load_scenario, run_interactive_scenario, validate_scenario
from growing_bench.interactive_judging import build_interaction_packet, score_interaction, validate_interaction_judgment
from growing_bench.interactive_self_test import run_interactive_self_test, suite_scenarios
from growing_bench.judging import build_packet as build_action_packet
from growing_bench.run_append import append_run


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "growing_bench" / "resources" / "interactive" / "code-reuse-helper-present.json"
INTERVENTION = ROOT / "examples" / "interventions" / "proportional-work.md"


def command(module: str, *parts: str) -> str:
    return json.dumps([sys.executable, "-m", module, *parts])


class InteractiveProductTests(unittest.TestCase):
    def test_public_interactive_schemas_are_valid_json(self) -> None:
        expected = {
            "interactive-scenario.schema.json": "growing-bench-interactive-scenario-1.0",
            "interaction-judgment.schema.json": "growing-bench-interaction-judgment-1.0",
            "interaction-score.schema.json": "growing-bench-interaction-score-1.0",
        }
        for name, version in expected.items():
            value = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual(version, value["properties"]["schema_version"]["const"])
    def test_balanced_suite_has_eight_valid_real_workspace_scenarios(self) -> None:
        scenarios = suite_scenarios("balanced")
        self.assertEqual(8, len(scenarios))
        self.assertEqual(8, len({load_scenario(path)["base_task_id"] for path in scenarios}))

    def test_scenario_rejects_single_turn_qa(self) -> None:
        value = load_scenario(SCENARIO)
        value["turns"] = value["turns"][:1]
        with self.assertRaisesRegex(ValueError, "at least two user turns"):
            validate_scenario(value)

    def test_command_adapter_runs_three_turns_in_one_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-interactive-") as name:
            output = Path(name) / "run"
            result = run_interactive_scenario(
                SCENARIO, output, agent="command",
                command_template=command(
                    "growing_bench.demo_interactive_agent", "{workspace}", "{prompt_file}", "{turn_index}",
                ),
            )
            self.assertEqual("completed_pending_judgment", result["status"])
            self.assertEqual(3, result["turn_count"])
            self.assertEqual("adapter_managed", result["session_persistence"])
            self.assertEqual(["src/report_export.py"], result["changes"]["changed_paths"])
            self.assertTrue(result["post_checks_passed"])
            events = [json.loads(line) for line in (output / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(3, sum(row["kind"] == "user_message" for row in events))
            self.assertEqual(3, sum(row["kind"] == "assistant_message" for row in events))
            self.assertFalse(any(row["kind"] == "user_message" for row in build_action_packet(output)["events"]))
            self.assertTrue((output / "turn-diffs" / "turn-01.diff").read_text(encoding="utf-8"))

    def test_replay_adapter_reapplies_intervention_policy_every_turn(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-interactive-policy-") as name:
            output = Path(name) / "run"
            run_interactive_scenario(
                SCENARIO, output, agent="command", intervention=INTERVENTION,
                command_template=command(
                    "growing_bench.demo_interactive_agent", "{workspace}", "{prompt_file}", "{turn_index}",
                ),
            )
            for index in range(1, 4):
                prompt = (output / "agent" / f"turn-{index:02d}" / "prompt.md").read_text(encoding="utf-8")
                self.assertEqual(1, prompt.count("## Session intervention policy"))
                self.assertIn("Before acting, identify the smallest set of steps", prompt)
                turn = json.loads((output / "agent" / f"turn-{index:02d}" / "turn.json").read_text(encoding="utf-8"))
                self.assertTrue(turn["intervention_policy_applied"])

    def test_interaction_judgment_is_quote_bound_and_does_not_infer_feelings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-interaction-judge-") as name:
            output = Path(name) / "run"
            run_interactive_scenario(
                SCENARIO, output, agent="command",
                command_template=command(
                    "growing_bench.demo_interactive_agent", "{workspace}", "{prompt_file}", "{turn_index}",
                ),
            )
            packet = build_interaction_packet(output)
            signals = [{
                "signal_id": f"{turn['move_id']}::{target}", "status": "honored",
                "evidence_refs": [packet["events"][-1]["event_id"]], "explanation": "Visible follow-through.",
                "confidence": 0.8,
            } for turn in packet["scenario"]["controller_turns"] for target in turn["targets"]]
            assistant = [row for row in packet["events"] if row["kind"] == "assistant_message"]
            spans = [{"span_id": f"S{index}", "event_id": event["event_id"], "quote": event["content"],
                      "label": "decision_relevant", "topic_id": None, "explanation": "Visible Agent response.", "confidence": 0.8}
                     for index, event in enumerate(assistant, start=1)]
            raw = {"schema_version": "growing-bench-interaction-judgment-1.0", "evaluator_id": "test", "confidence": 0.8,
                   "spans": spans, "signals": signals}
            judgment = validate_interaction_judgment(raw, packet)
            score = score_interaction(packet, judgment)
            self.assertNotIn("satisfaction", score)
            self.assertEqual(1.0, score["state_update_success"])
            self.assertGreater(score["scenario_pressure"]["correction_turn_count"], 0)
            self.assertGreater(score["scenario_pressure"]["pressure_points"], 0)
            self.assertEqual(0, score["observed_agent_burden_points"])
            raw["spans"][0]["quote"] = "invented feeling"
            with self.assertRaisesRegex(ValueError, "quote is absent"):
                validate_interaction_judgment(raw, packet)
            raw["spans"][0]["quote"] = assistant[0]["content"]
            raw["signals"][0]["evidence_refs"] = [packet["events"][0]["event_id"]]
            with self.assertRaisesRegex(ValueError, "subsequent Agent"):
                validate_interaction_judgment(raw, packet)

    def test_interactive_self_test_report_and_living_append(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-interactive-e2e-") as name:
            root = Path(name)
            result = run_interactive_self_test(
                INTERVENTION, root / "run", scenario_paths=[SCENARIO], agent="command", judge="command",
                command_template=command(
                    "growing_bench.demo_interactive_agent", "{workspace}", "{prompt_file}", "{turn_index}",
                ),
                judge_command_template=command("growing_bench.demo_universal_judge", "{prompt_file}"),
                strict=True, open_report=False,
            )
            self.assertEqual("completed", result["status"])
            self.assertEqual(2, len(result["results"]))
            self.assertEqual(1.0, result["summary"]["baseline"]["task_success"])
            report = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("Did the Agent update with the user?", report)
            self.assertIn("Stale narrative events", report)
            self.assertIn("Scenario pressure", report)
            self.assertIn("Observed Agent burden", report)
            self.assertNotIn(">Interaction burden<", report)
            appended = append_run(root / "run", root / "case", "A real interactive regression", check=True)
            self.assertEqual("local_draft", appended["status"])
            self.assertTrue(appended["preflight"]["local_use_allowed"])
            self.assertEqual([], appended["preflight"]["missing"])
            self.assertTrue((root / "case" / "scenario.json").is_file())
            self.assertTrue((root / "case" / "trajectory.jsonl").is_file())
            self.assertTrue((root / "case" / "reference" / "src" / "report_export.py").is_file())


if __name__ == "__main__":
    unittest.main()
