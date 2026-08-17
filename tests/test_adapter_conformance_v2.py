from __future__ import annotations

import json
import unittest
from pathlib import Path

from growing_bench.quality import trajectory_completeness
from growing_bench.trajectory import normalize_agent_events


ROOT = Path(__file__).resolve().parent / "fixtures" / "adapters"


def records(adapter: str) -> list[dict]:
    path = ROOT / f"conformance-{adapter}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AdapterConformanceV2Tests(unittest.TestCase):
    def test_each_adapter_preserves_command_write_failure_duration_and_status(self) -> None:
        for adapter in ("codex", "claude-code", "openclaw", "command"):
            with self.subTest(adapter=adapter):
                events = normalize_agent_events(adapter, records(adapter))
                kinds = [row["kind"] for row in events]
                self.assertIn("command_start", kinds)
                self.assertIn("command_result", kinds)
                self.assertIn("file_write", kinds)
                result = next(row for row in events if row["kind"] == "command_result")
                self.assertEqual(result["status"], "failure")
                self.assertGreater(float(result["duration_ms"]), 0)
                completeness = trajectory_completeness(adapter, events)
                self.assertTrue(completeness["observed"]["exit_status"])
                self.assertTrue(completeness["observed"]["duration"])

    def test_missing_native_events_remain_visible(self) -> None:
        events = normalize_agent_events("claude-code", [json.loads(line) for line in (ROOT / "claude-code.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()])
        completeness = trajectory_completeness("claude-code", events)
        self.assertIn("command_start", completeness["missing_supported_events"])
        self.assertIn("file_write", completeness["missing_supported_events"])


if __name__ == "__main__":
    unittest.main()
