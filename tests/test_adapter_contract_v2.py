from __future__ import annotations

import json
import unittest

from growing_bench.quality import COMMON_EVENT_CONTRACT, adapter_capabilities, isolation_profile, trajectory_completeness, validate_isolation
from growing_bench.trajectory import normalize_agent_events


class AdapterContractV2Tests(unittest.TestCase):
    def test_all_public_adapters_declare_common_contract(self) -> None:
        for adapter in ("codex", "claude-code", "openclaw", "command"):
            self.assertEqual(set(adapter_capabilities(adapter)), set(COMMON_EVENT_CONTRACT))

    def test_custom_declared_failure_and_duration_are_preserved(self) -> None:
        records = [{
            "text": json.dumps({"events": [
                {"kind": "command_start", "content": "python check.py", "status": "started"},
                {"kind": "command_result", "content": "python check.py", "status": "failure", "visible_output": "boom", "duration_ms": 12},
                {"kind": "file_write", "target": "answer.txt", "status": "success", "content": "write"},
            ]}),
            "received_at": "2026-01-01T00:00:00Z",
            "offset_seconds": 0.0,
        }]
        events = normalize_agent_events("command", records)
        self.assertEqual(events[1]["status"], "failure")
        self.assertEqual(events[1]["duration_ms"], 12)
        completeness = trajectory_completeness("command", events)
        self.assertLess(completeness["score"], 1.0)
        self.assertIn("file_read", completeness["missing_supported_events"])

    def test_isolation_modes_are_explicit_and_fail_closed(self) -> None:
        self.assertEqual(isolation_profile("command", "copy")["requested_mode"], "copy")
        self.assertTrue(isolation_profile("codex", "agent-native")["agent_native_required"])
        with self.assertRaisesRegex(ValueError, "supported only by the Codex"):
            validate_isolation("claude-code", "agent-native")

    def test_plain_stdout_does_not_become_fake_actions(self) -> None:
        records = [{"text": "I probably read and tested everything", "received_at": "2026-01-01T00:00:00Z", "offset_seconds": 0.0}]
        self.assertEqual(normalize_agent_events("command", records), [])
        completeness = trajectory_completeness("command", [])
        self.assertEqual(completeness["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
