from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from growing_bench.pipeline import ingest, preflight


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples" / "submissions" / "bounded-review-decision.md"


class PublicPipelineTests(unittest.TestCase):
    def test_new_case_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-pipeline-") as name:
            value = preflight(CASE, Path(name) / "tracks")
        self.assertEqual(value["status"], "ready_for_materialization")
        self.assertTrue(value["checks"]["environment_executable"])
        self.assertTrue(value["checks"]["pair_metadata_present"])

    @unittest.skipUnless(shutil.which("pdflatex"), "requires pdflatex; exercised by workspace-admission CI")
    def test_ingest_materialize_validate_real_latex_fixture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-pipeline-") as name:
            value = ingest(CASE, Path(name) / "tracks", materialize=True, validate=True)
            task = json.loads(Path(value["materialize"]["task"]).read_text(encoding="utf-8"))
        self.assertEqual(value["validate"]["status"], "validated")
        self.assertEqual(task["kind"], "internal_review")
        self.assertEqual(task["living_case"]["reference_status"], "silver_pending")


if __name__ == "__main__":
    unittest.main()
