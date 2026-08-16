from __future__ import annotations

import json
import unittest
from pathlib import Path

from growing_bench.trajectory import normalize_agent_events


ROOT = Path(__file__).resolve().parent / "fixtures" / "adapters"


def records(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


class AdapterGoldenEventTests(unittest.TestCase):
    def test_codex_stream_preserves_test_duration_and_message(self) -> None:
        rows = normalize_agent_events("codex", records("codex"))
        self.assertEqual([row["kind"] for row in rows], ["command_start", "test_result", "assistant_message"])
        self.assertEqual(rows[1]["duration_ms"], 1000.0)
        self.assertEqual(rows[1]["visible_output"], "OK")

    def test_claude_stream_preserves_read_and_visible_reasoning(self) -> None:
        rows = normalize_agent_events("claude-code", records("claude-code"))
        self.assertEqual([row["kind"] for row in rows], ["file_read", "assistant_message", "artifact"])
        self.assertEqual(rows[-1]["usage"]["output_tokens"], 5)

    def test_openclaw_declared_events_keep_file_and_test_evidence(self) -> None:
        rows = normalize_agent_events("openclaw", records("openclaw"))
        self.assertEqual([row["kind"] for row in rows], ["file_read", "file_write", "test_result"])
        self.assertEqual(rows[-1]["duration_ms"], 25)


if __name__ == "__main__":
    unittest.main()
