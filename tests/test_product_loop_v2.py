from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growing_bench import cli
from growing_bench.calibration import run_gate_calibration
from growing_bench.run_append import append_run
from growing_bench.self_test import run_self_test


class ProductLoopV2Tests(unittest.TestCase):
    def _task(self, root: Path) -> Path:
        fixture = root / "fixture"
        fixture.mkdir()
        (fixture / "check.py").write_text(
            "from pathlib import Path\n"
            "p=Path('answer.txt')\n"
            "raise SystemExit(0 if p.is_file() and p.read_text()=='done\\n' else 1)\n",
            encoding="utf-8",
        )
        task = {
            "schema_version": "growing-bench-task-2.0",
            "task_id": "product-loop-fixture",
            "title": "Write the bounded answer",
            "kind": "code",
            "fixture": "fixture",
            "prompt": "Create answer.txt containing done followed by a newline and run check.py.",
            "authorization": "Modify only answer.txt.",
            "checks": [{"name": "focused-check", "command": [sys.executable, "check.py"]}],
            "baseline_expectation": "failing",
            "expected_failure": {"check": "focused-check", "returncode": 1, "contains": ""},
            "allowed_paths": ["answer.txt"],
            "forbidden_paths": [],
            "ignore_paths": ["__pycache__"],
            "required_artifacts": ["answer.txt"],
            "completion_criteria": [
                {
                    "criterion_id": "C1",
                    "description": "answer.txt contains the requested value",
                    "kind": "check",
                    "check": "focused-check",
                    "weight": 1.0,
                }
            ],
            "budget": {"human_minutes": 10, "machine_minutes": 5, "compute_cost": 1},
        }
        path = root / "task.json"
        path.write_text(json.dumps(task), encoding="utf-8")
        return path

    def _strict_run(self, root: Path) -> tuple[dict, Path]:
        task = self._task(root)
        intervention = root / "SKILL.md"
        intervention.write_text("Use the smallest sufficient edit.\n", encoding="utf-8")
        agent_command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
        judge_command = json.dumps([sys.executable, "-m", "growing_bench.demo_judge", "{prompt_file}"])
        run_dir = root / "run"
        result = run_self_test(
            intervention,
            run_dir,
            task_paths=[task],
            agent="command",
            judge="command",
            command_template=agent_command,
            judge_command_template=judge_command,
            strict=True,
            open_report=False,
        )
        return result, run_dir

    def test_strict_self_test_records_agreement_cost_sources_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-product-loop-") as name:
            result, run_dir = self._strict_run(Path(name))
            report = Path(result["report"]).read_text(encoding="utf-8")
            score = result["results"][0]
            agreement = score["judge"]["agreement"]
            self.assertEqual(result["status"], "completed")
            self.assertIn("action_extraction_jaccard", agreement)
            self.assertIn("label_agreement", agreement)
            self.assertIn(score["actions"][0]["machine_time_source"], {"observed", "estimated", "imputed"})
            self.assertIn("machine_time_method", score["actions"][0])
            self.assertIn("Judge calibration", report)
            self.assertIn("Trajectory completeness", report)
            self.assertIn("Evidence", report)
            self.assertTrue((run_dir / "judgments" / score["run_name"] / "evaluator-b.json").is_file())

    def test_append_preserves_both_conditions_and_actionable_preflight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-product-append-") as name:
            root = Path(name)
            _, run_dir = self._strict_run(root)
            appended = append_run(run_dir, root / "case", "Bounded answer experience", redact=True, check=True)
            comparison = json.loads((root / "case" / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual({row["condition"] for row in comparison["runs"]}, {"baseline", "intervention"})
            self.assertTrue((root / "case" / "evidence" / "baseline" / "trajectory.jsonl").is_file())
            self.assertTrue((root / "case" / "evidence" / "intervention" / "judgment.json").is_file())
            self.assertIn("issues", appended["preflight"])

    def test_calibration_has_ten_decision_boundaries(self) -> None:
        result = run_gate_calibration()
        self.assertEqual(result["case_count"], 20)
        self.assertEqual(len({row["pair_id"] for row in result["cases"]}), 10)
        self.assertEqual(result["failed"], 0)

    def test_invalid_utf8_ingest_check_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-invalid-utf8-") as name:
            case = Path(name) / "case.md"
            case.write_bytes(b"\xff\xfe")
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", ["growing-bench", "ingest", str(case), "--check"]):
                with contextlib.redirect_stdout(stdout):
                    code = cli.main()
            self.assertEqual(code, 0)
            self.assertIn("not valid UTF-8", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
