from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from growing_bench.agents import probe_agent
from growing_bench.execution import run_task


ROOT = Path(__file__).resolve().parents[1]


class AgentAdapterTests(unittest.TestCase):
    def test_command_adapter_runs_real_workspace_task(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-bench-adapter-") as name:
            output = Path(name) / "run"
            command = json.dumps([
                sys.executable,
                "-m",
                "growing_bench.demo_agent",
                "{workspace}",
            ])
            result = run_task(
                ROOT / "examples" / "tasks" / "adapter-smoke.json",
                output,
                agent="command",
                command_template=command,
            )
            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["post_checks_passed"])
            self.assertTrue(result["allowed_paths_ok"])
            self.assertEqual(result["changes"]["added"], ["answer.txt"])
            self.assertTrue((output / "trajectory.jsonl").is_file())
            self.assertTrue((output / "agent" / "stdout.log").is_file())

    def test_missing_builtin_is_reported_without_running_it(self) -> None:
        status = probe_agent("openclaw")
        self.assertEqual(status["agent"], "openclaw")
        self.assertIsInstance(status["available"], bool)

    def test_ignored_path_is_a_directory_tree(self) -> None:
        fixture = ROOT / "fixtures" / "agent_adapter_smoke" / "__pycache__"
        fixture.mkdir(exist_ok=True)
        (fixture / "ignored.pyc").write_bytes(b"ignored")
        try:
            with tempfile.TemporaryDirectory(prefix="growing-bench-ignore-") as name:
                output = Path(name) / "run"
                command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
                result = run_task(ROOT / "examples" / "tasks" / "adapter-smoke.json", output, agent="command", command_template=command)
                self.assertNotIn("__pycache__/ignored.pyc", result["changes"]["changed_paths"])
        finally:
            shutil.rmtree(fixture, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
