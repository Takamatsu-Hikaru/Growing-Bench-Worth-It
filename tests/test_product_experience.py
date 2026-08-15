from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from growing_bench.agents import run_agent
from growing_bench.smoke import run_smoke


class ProductExperienceTests(unittest.TestCase):
    def test_report_leads_with_outcomes_and_action_value(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-report-") as name:
            result = run_smoke(Path(name) / "run")
            report = Path(result["report"]).read_text(encoding="utf-8")
        self.assertIn("Was the work worth it?", report)
        self.assertIn("Necessary-action recall", report)
        self.assertIn("Avoidable human time", report)
        self.assertIn("Action timeline", report)
        self.assertIn("ROI is retained as a derived diagnostic", report)

    def test_command_adapter_timeout_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-timeout-") as name:
            root = Path(name); workspace = root / "workspace"; workspace.mkdir()
            command = json.dumps([sys.executable, "-c", "import time; time.sleep(2)"])
            result = run_agent("command", "wait", workspace, root / "artifacts", timeout=0.05, command_template=command)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNone(result["returncode"])

    def test_missing_agent_cli_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-missing-") as name:
            root = Path(name); workspace = root / "workspace"; workspace.mkdir()
            with mock.patch("growing_bench.agents._executable", return_value=None):
                with self.assertRaisesRegex(FileNotFoundError, "not installed or not on PATH"):
                    run_agent("openclaw", "work", workspace, root / "artifacts")


if __name__ == "__main__":
    unittest.main()
