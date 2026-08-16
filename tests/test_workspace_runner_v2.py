from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from growing_bench.task_contract import evaluate_completion
from growing_bench.trajectory import normalize_agent_events


class WorkspaceRunnerV2Tests(unittest.TestCase):
    def test_codex_command_and_file_events_are_visible(self) -> None:
        records = [
            {
                "text": json.dumps({
                    "type": "item.started",
                    "item": {"id": "c1", "type": "command_execution", "command": "python check.py"},
                }),
                "received_at": "2026-08-16T00:00:00Z",
                "offset_seconds": 1.0,
            },
            {
                "text": json.dumps({
                    "type": "item.completed",
                    "item": {
                        "id": "c1", "type": "command_execution", "command": "python check.py",
                        "exit_code": 0, "aggregated_output": "ok",
                    },
                }),
                "received_at": "2026-08-16T00:00:02Z",
                "offset_seconds": 3.0,
            },
            {
                "text": json.dumps({
                    "type": "item.completed",
                    "item": {"id": "f1", "type": "file_change", "changes": [{"path": "answer.txt"}]},
                }),
                "received_at": "2026-08-16T00:00:03Z",
                "offset_seconds": 4.0,
            },
        ]
        events = normalize_agent_events("codex", records)
        self.assertEqual([row["kind"] for row in events], ["command_start", "command_result", "file_write"])
        self.assertEqual(events[1]["duration_ms"], 2000.0)
        self.assertEqual(events[1]["visible_output"], "ok")

    def test_machine_and_semantic_completion_remain_separate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-completion-") as name:
            workspace = Path(name)
            (workspace / "answer.txt").write_text("done\n", encoding="utf-8")
            task = {
                "required_artifacts": ["answer.txt"],
                "completion_criteria": [
                    {
                        "criterion_id": "C1", "description": "check passes", "kind": "check",
                        "check": "answer-check", "weight": 1,
                    },
                    {
                        "criterion_id": "C2", "description": "answer is proportionate", "kind": "semantic",
                        "weight": 1,
                    },
                ],
            }
            rows, machine, pending = evaluate_completion(
                task, workspace, [{"name": "answer-check", "passed": True}]
            )
        self.assertTrue(machine)
        self.assertTrue(pending)
        self.assertEqual([row["status"] for row in rows], ["passed", "passed", "pending"])


if __name__ == "__main__":
    unittest.main()
