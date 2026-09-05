from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growing_bench.agents import diagnose_agent_failure, probe_agent, run_agent
from growing_bench.execution import run_task


ROOT = Path(__file__).resolve().parents[1]


class AgentAdapterTests(unittest.TestCase):
    def test_zero_exit_api_error_is_an_agent_stage_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-bench-silent-agent-") as name:
            root = Path(name)
            with mock.patch("growing_bench.agents._build_command", return_value=(["claude"], None)):
                with mock.patch(
                    "growing_bench.agents._run_captured",
                    return_value=(
                        0, "API Error: 402 no active subscription\n", "", "completed", 0.1,
                        "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", [],
                    ),
                ):
                    with mock.patch("growing_bench.agents.probe_agent", return_value={"version": "test"}):
                        result = run_agent("claude-code", "work", root, root / "agent")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure"]["code"], "agent_api_http_402")
        self.assertIn("subscription", result["failure"]["message"])

    def test_empty_visible_trajectory_is_not_completed(self) -> None:
        failure = diagnose_agent_failure("completed", 0, "done", "", "done", [])
        self.assertEqual(failure["code"], "agent_empty_trajectory")

    def test_plain_cli_output_gets_observed_outer_process_events(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-bench-plain-cli-") as name:
            root = Path(name)
            command = json.dumps([sys.executable, "-c", "print('plain final')"])
            result = run_agent(
                "command", "work", root, root / "agent", command_template=command
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failure"], None)
        kinds = [row["kind"] for row in result["visible_events"]]
        self.assertEqual(kinds, ["command_start", "command_result", "assistant_message"])

    def test_openai_compatible_probe_does_not_expose_key(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "GROWING_BENCH_BASE_URL": "https://example.test/v1",
                "GROWING_BENCH_API_KEY_ENV": "TEST_PROVIDER_KEY",
                "TEST_PROVIDER_KEY": "secret-value",
            },
            clear=False,
        ):
            status = probe_agent("openai-compatible")
        self.assertTrue(status["available"])
        self.assertEqual(status["api_key_env"], "TEST_PROVIDER_KEY")
        self.assertNotIn("secret-value", str(status))

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
