from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from growing_bench.cli import main
from growing_bench.execution import run_task


ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def test_release_manifest_and_catalog_agree(self) -> None:
        tasks = [json.loads(x) for x in (ROOT / "data/tasks/tasks.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        pairs = json.loads((ROOT / "data/tasks/pairs.json").read_text(encoding="utf-8"))
        release = json.loads((ROOT / "data/PUBLIC_RELEASE.json").read_text(encoding="utf-8"))
        self.assertEqual(len(tasks), 34)
        self.assertEqual(pairs["matched_group_count"], 17)
        self.assertEqual({p["group_type"] for p in pairs["pairs"]}, {"pair", "triad", "singleton"})
        self.assertTrue(all(t["release_status"] == "released" and t["publication"]["release_eligible"] for t in tasks))
        self.assertEqual(release["release"], "0.1.0")

    def test_init_case_then_check_writes_only_template(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-init-") as name:
            target = Path(name) / "my-case.md"
            old = sys.argv
            try:
                sys.argv = ["growing-bench", "init-case", "my-case", "--output", str(target)]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old
            self.assertTrue(target.is_file())

    def test_adapter_rejects_out_of_scope_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-scope-") as name:
            script = Path(name) / "agent.py"
            script.write_text("import pathlib,sys; p=pathlib.Path(sys.argv[1]); (p/'answer.txt').write_text('done\\n'); (p/'extra.txt').write_text('no')\n", encoding="utf-8")
            output = Path(name) / "run"
            command = json.dumps([sys.executable, str(script), "{workspace}"])
            result = run_task(ROOT / "examples/tasks/adapter-smoke.json", output, agent="command", command_template=command)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["unexpected_changed_paths"], ["extra.txt"])

    @unittest.skipUnless(os.name == "nt", "Windows console regression")
    def test_windows_cli_utf8_never_tracebacks(self) -> None:
        env = {**os.environ, "PYTHONIOENCODING": "cp936"}
        completed = subprocess.run([sys.executable, "-m", "growing_bench", "--json", "doctor"], cwd=ROOT, env=env, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"Traceback", completed.stderr)
        json.loads(completed.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
