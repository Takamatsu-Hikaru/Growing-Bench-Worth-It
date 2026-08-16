from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from growing_bench.corpus import validate_corpus


ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / "tracks" / "workspace-v0.2"


class WorkspaceValidityV2Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pdflatex"), "requires pdflatex; exercised by workspace-admission CI")
    def test_all_packages_separate_visible_checks_and_reject_known_wrong_alternatives(self) -> None:
        result = validate_corpus(TRACK)
        self.assertEqual(result["status"], "package_admission_passed")
        self.assertEqual(result["admitted_count"], 50)
        self.assertFalse(result["semantic_evaluation_complete"])
        for task in result["tasks"]:
            self.assertTrue(task["checks"]["semantic_oracle_not_agent_visible"], task["task_id"])
            self.assertTrue(task["checks"]["known_wrong_alternative_rejected"], task["task_id"])

    def test_writing_and_review_public_checks_contain_no_target_semantics(self) -> None:
        for task_path in TRACK.glob("tasks/*/task.json"):
            task = json.loads(task_path.read_text(encoding="utf-8"))
            if task["kind"] not in {"writing", "internal_review", "external_peer_review"}:
                continue
            spec = json.loads((task_path.parent / "reference" / "hidden_spec.json").read_text(encoding="utf-8"))
            visible = "\n".join(path.read_text(encoding="utf-8") for path in (task_path.parent / "fixture" / "checks").glob("*.py"))
            secrets = spec.get("required_concepts", []) + spec.get("forbidden_claims", []) + spec.get("required_evidence_ids", []) + spec.get("forbidden_required_actions", [])
            self.assertTrue(all(str(secret) not in visible for secret in secrets), task["task_id"])

    def test_streaming_zip_check_covers_declared_behavior(self) -> None:
        directory = TRACK / "tasks" / "workspace-v0.2--code-native--streaming-zip-required"
        check = (directory / "fixture" / "checks" / "check.py").read_text(encoding="utf-8")
        for evidence in ("unbounded source read", "unsafe name accepted", "write failure was swallowed", "namelist"):
            self.assertIn(evidence, check)


if __name__ == "__main__":
    unittest.main()
