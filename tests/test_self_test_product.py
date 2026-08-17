from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growing_bench import cli
from growing_bench.calibration import run_gate_calibration
from growing_bench.ingest_experience import enrich_preflight
from growing_bench.judging import JUDGMENT_SCHEMA_VERSION, validate_judgment
from growing_bench.quality import trajectory_completeness
from growing_bench.run_append import append_run
from growing_bench.self_test import run_self_test


class SelfTestProductTests(unittest.TestCase):
    def _task(self, root: Path) -> Path:
        fixture = root / "fixture"; fixture.mkdir()
        (fixture / "check.py").write_text(
            "from pathlib import Path\n"
            "p=Path('answer.txt')\n"
            "raise SystemExit(0 if p.is_file() and p.read_text()=='done\\n' else 1)\n",
            encoding="utf-8",
        )
        task = {
            "schema_version": "growing-bench-task-2.0",
            "task_id": "self-test-fixture",
            "title": "Write the bounded answer",
            "kind": "code",
            "fixture": "fixture",
            "prompt": "Create answer.txt containing exactly done followed by a newline, then run check.py.",
            "authorization": "Modify only answer.txt.",
            "checks": [{"name": "focused-check", "command": [sys.executable, "check.py"]}],
            "baseline_expectation": "failing",
            "expected_failure": {"check": "focused-check", "returncode": 1, "contains": ""},
            "allowed_paths": ["answer.txt"],
            "forbidden_paths": [],
            "ignore_paths": ["__pycache__"],
            "required_artifacts": ["answer.txt"],
            "completion_criteria": [
                {"criterion_id": "C1", "description": "answer.txt contains the requested value", "kind": "check", "check": "focused-check", "weight": 1.0}
            ],
            "budget": {"human_minutes": 10, "machine_minutes": 5, "compute_cost": 1},
        }
        path = root / "task.json"; path.write_text(json.dumps(task), encoding="utf-8")
        return path

    def test_offline_self_test_runs_baseline_intervention_judge_report_and_append(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-self-test-") as name:
            root = Path(name); task = self._task(root)
            intervention = root / "SKILL.md"; intervention.write_text("Use the smallest sufficient edit.\n", encoding="utf-8")
            agent_command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
            judge_command = json.dumps([sys.executable, "-m", "growing_bench.demo_judge", "{prompt_file}"])
            result = run_self_test(
                intervention, root / "run", task_paths=[task], agent="command", judge="command",
                command_template=agent_command, judge_command_template=judge_command, open_report=False,
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(result["results"]), 2)
            self.assertTrue(Path(result["report"]).is_file())
            report = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("Baseline and intervention", report)
            self.assertIn("Observed elapsed time", report)
            appended = append_run(result_dir := root / "run", root / "case", "Repeated bounded answer work", redact=True, check=True)
            self.assertTrue(Path(appended["case"]).is_file())
            self.assertEqual(appended["status"], "local_draft")
            self.assertEqual(result_dir, root / "run")

    def test_necessary_gate_calibration_is_complete(self) -> None:
        result = run_gate_calibration()
        self.assertGreaterEqual(result["case_count"], 12)
        self.assertEqual(result["failed"], 0)

    def test_necessary_without_requirement_is_downgraded_to_unresolved(self) -> None:
        packet = {
            "task": {"completion_criteria": [{"criterion_id": "C1"}]},
            "events": [{"event_id": "e1", "kind": "assistant_message", "content": "audit"}],
        }
        raw = {
            "schema_version": JUDGMENT_SCHEMA_VERSION, "evaluator_id": "a", "semantic_success": 1,
            "confidence": 0.8, "missed_actions": [],
            "actions": [{"action_id": "A1", "description": "Broad audit", "action_type": "analysis", "status": "completed", "label": "necessary", "atomic": True, "requirement_id": None, "omission_consequence": "Maybe risky", "evidence_refs": ["e1"], "explanation": "insurance", "cheaper_substitute": None, "estimated_machine_minutes": 1, "confidence": 0.7}],
        }
        result = validate_judgment(raw, packet)
        self.assertEqual(result["actions"][0]["label"], "unresolved")

    def test_completeness_exposes_missing_adapter_events(self) -> None:
        result = trajectory_completeness("claude-code", [{"kind": "file_read", "status": "success"}])
        self.assertLess(result["score"], 1.0)
        self.assertIn("assistant_message", result["missing_supported_events"])

    def test_failed_run_exit_code_is_nonzero(self) -> None:
        with mock.patch.object(cli, "run_task", return_value={"status": "failed", "task_id": "x", "post_checks_passed": False, "allowed_paths_ok": True, "artifacts": {}}):
            with mock.patch.object(sys, "argv", ["growing-bench", "run", "task.json", "--output", "out"]):
                self.assertEqual(cli.main(), 1)

    def test_ingest_explains_encoding_damage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-ingest-quality-") as name:
            case = Path(name) / "case.md"; case.write_text("broken �� text", encoding="utf-8")
            value = enrich_preflight({"status": "needs_curation", "missing": ["section:Task"], "checks": {}}, case)
        codes = {row["code"] for row in value["issues"]}
        self.assertIn("encoding_damage", codes)
        self.assertIn("missing_field", codes)


if __name__ == "__main__":
    unittest.main()
