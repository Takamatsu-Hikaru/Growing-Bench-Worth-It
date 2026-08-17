from __future__ import annotations

import sys
import unittest
from unittest import mock

from growing_bench import cli


class CliExitContractTests(unittest.TestCase):
    def test_successful_workspace_run_returns_zero(self) -> None:
        value = {
            "status": "completed",
            "task_id": "ok",
            "post_checks_passed": True,
            "allowed_paths_ok": True,
            "artifacts": {"trajectory": "trajectory.jsonl"},
        }
        with mock.patch.object(cli, "run_task", return_value=value):
            with mock.patch.object(sys, "argv", ["growing-bench", "run", "task.json", "--output", "out"]):
                self.assertEqual(cli.main(), 0)

    def test_agent_failure_returns_one(self) -> None:
        value = {
            "status": "failed",
            "task_id": "bad",
            "post_checks_passed": False,
            "allowed_paths_ok": True,
            "artifacts": {},
        }
        with mock.patch.object(cli, "run_task", return_value=value):
            with mock.patch.object(sys, "argv", ["growing-bench", "run", "task.json", "--output", "out"]):
                self.assertEqual(cli.main(), 1)

    def test_partial_self_test_with_report_returns_nonzero_by_default(self) -> None:
        value = {
            "status": "partial_failed",
            "summary": {
                "baseline": {"task_success": 1.0, "avoidable_action_count": 0, "missed_necessary_count": 0},
                "intervention": {"task_success": 0.5, "avoidable_action_count": 1, "missed_necessary_count": 1},
            },
            "report": "report.html",
            "results": [{"task_id": "one"}],
            "failures": [{"run": "two", "stage": "agent", "status": "failed"}],
        }
        with mock.patch.object(cli, "run_self_test", return_value=value):
            with mock.patch.object(
                sys,
                "argv",
                ["growing-bench", "self-test", "skill.md", "--output", "out", "--no-open"],
            ):
                self.assertEqual(cli.main(), 1)

    def test_judge_failure_uses_exit_three(self) -> None:
        value = {
            "status": "partial_failed",
            "summary": {
                "baseline": {"task_success": 0.0, "avoidable_action_count": 0, "missed_necessary_count": 0},
                "intervention": {"task_success": 0.0, "avoidable_action_count": 0, "missed_necessary_count": 0},
            },
            "report": "report.html",
            "results": [],
            "failures": [{"run": "one", "stage": "judge", "status": "invalid JSON"}],
        }
        with mock.patch.object(cli, "run_self_test", return_value=value):
            with mock.patch.object(
                sys,
                "argv",
                ["growing-bench", "self-test", "skill.md", "--output", "out", "--no-open"],
            ):
                self.assertEqual(cli.main(), 3)


if __name__ == "__main__":
    unittest.main()
