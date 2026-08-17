from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class HuggingFaceExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="growing-hf-", ignore_cleanup_errors=True)
        cls.output = Path(cls.temp.name) / "dataset"
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "export_huggingface.py"), "--output", str(cls.output)],
            cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_card_contains_article_and_three_local_images(self):
        card = (self.output / "README.md").read_text(encoding="utf-8")
        self.assertIn("Correct isn't enough. Was the work worth it?", card)
        self.assertIn("Codex repeatedly tried to add exactly these statements", card)
        for name in ("growing-bench-hero.png", "growing-bench-architecture.jpg", "how-growing-bench-grows.jpg"):
            self.assertIn(f"assets/{name}", card)
            self.assertTrue((self.output / "assets" / name).is_file())
        self.assertNotIn("releases/download/v0.2.0-rc1", card)

    def test_workspace_dataset_and_packages_cover_all_fifty_tasks(self):
        rows = read_jsonl(self.output / "data" / "workspace_tasks.jsonl")
        packages = sorted((self.output / "workspace_packages").glob("*.zip"))
        self.assertEqual(len(rows), 50)
        self.assertEqual(len(packages), 50)
        self.assertEqual(len({row["task_id"] for row in rows}), 50)
        for row in rows:
            archive = self.output / row["workspace_archive"]
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as value:
                names = value.namelist()
            prefix = row["task_id"] + "/"
            self.assertIn(prefix + "task.json", names)
            self.assertTrue(any(name.startswith(prefix + "fixture/") for name in names))

    def test_families_calibration_actions_and_supplemental_counts(self):
        self.assertEqual(len(read_jsonl(self.output / "data" / "scenario_families.jsonl")), 25)
        trajectories = read_jsonl(self.output / "data" / "calibration_trajectories.jsonl")
        self.assertEqual(len(trajectories), 8)
        self.assertEqual(len(read_jsonl(self.output / "data" / "calibration_scores.jsonl")), 8)
        self.assertEqual(len(read_jsonl(self.output / "data" / "consensus_references.jsonl")), 8)
        self.assertGreater(len(read_jsonl(self.output / "data" / "action_scores.jsonl")), 8)
        self.assertEqual(len(read_jsonl(self.output / "supplemental" / "static_qa" / "tasks.jsonl")), 34)
        self.assertEqual(len(read_jsonl(self.output / "supplemental" / "static_qa" / "responses.jsonl")), 544)
        self.assertTrue(all(row["run_name"].endswith("-rc1") for row in trajectories))

    def test_manifest_matches_exported_files(self):
        manifest = json.loads((self.output / "dataset_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["dataset_id"], "takamatsu-hikaru/Growing-Bench-Worth-It")
        self.assertEqual(manifest["counts"]["workspace_tasks"], 50)
        self.assertEqual(manifest["counts"]["scenario_families"], 25)
        self.assertEqual(manifest["counts"]["calibration_trajectories"], 8)
        self.assertEqual(manifest["counts"]["static_qa_responses"], 544)


if __name__ == "__main__":
    unittest.main()
