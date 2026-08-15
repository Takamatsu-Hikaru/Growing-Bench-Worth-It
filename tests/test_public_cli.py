from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from growing_bench.living import ingest_case
from growing_bench.smoke import run_smoke


ROOT = Path(__file__).resolve().parents[1]


class PublicCliTests(unittest.TestCase):
    def test_frozen_smoke_recomputes_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-bench-smoke-") as name:
            result = run_smoke(Path(name) / "output")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["trajectory_count"], 4)
            self.assertFalse(result["uses_external_model"])
            self.assertTrue(Path(result["report"]).is_file())

    def test_new_markdown_case_stages_and_materializes(self) -> None:
        source = (ROOT / "living" / "examples" / "code_case.md").read_text(encoding="utf-8")
        source = source.replace("reviewed-markdown-avoid-extra-sanitizer", "public-cli-new-case")
        source = source.replace("wave-2026-08", "public-cli-test-track")
        with tempfile.TemporaryDirectory(prefix="growing-bench-ingest-") as name:
            root = Path(name)
            case = root / "new-case.md"
            case.write_text(source, encoding="utf-8")
            result = ingest_case(case, root / "tracks", materialize=True)
            self.assertEqual(result["ingest"]["status"], "ready_for_materialization")
            task = Path(result["materialize"]["task"])
            self.assertTrue(task.is_file())
            payload = json.loads(task.read_text(encoding="utf-8"))
            self.assertEqual(payload["task_id"], "living-public-cli-test-track--public-cli-new-case")


if __name__ == "__main__":
    unittest.main()
