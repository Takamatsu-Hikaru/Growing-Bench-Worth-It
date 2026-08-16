from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "workspace-v0.2-calibration"
RELEASE = ROOT / "data" / "releases" / "workspace-v0.2-calibration"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class ReleaseConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = read_json(RELEASE / "run-card.json")
        cls.lineage = read_json(RELEASE / "source-run-map.json")["items"]
        cls.packets = read_json(RELEASE / "packets.json")["items"]

    def test_run_card_packets_and_public_trajectories_share_one_source_map(self):
        card_pairs = [(row["run"], row["task_id"]) for row in self.card["runs"]]
        lineage_pairs = [(row["run_name"], row["task_id"]) for row in self.lineage]
        self.assertEqual(card_pairs, lineage_pairs)
        self.assertEqual(len(card_pairs), self.card["task_count"])
        self.assertEqual(len(self.packets), len(card_pairs))
        self.assertTrue(all(run.endswith("-rc1") for run, _ in card_pairs))
        self.assertEqual(
            [row["item_id"] for row in self.packets],
            [row["item_id"] for row in self.lineage],
        )
        trajectory_dirs = sorted(
            path.name for path in (RELEASE / "trajectories").iterdir() if path.is_dir()
        )
        self.assertEqual(trajectory_dirs, sorted(run for run, _ in card_pairs))
        for row in self.lineage:
            run_dir = RELEASE / "trajectories" / row["run_name"]
            self.assertEqual(
                (RELEASE / row["trajectory"]).resolve(),
                (run_dir / "trajectory.jsonl").resolve(),
            )
            summary = read_json(run_dir / "summary.json")
            self.assertEqual(summary["task_id"], row["task_id"])
            self.assertEqual(summary["status"], "completed_silver_judged")
            self.assertEqual(summary["evaluation_status"], "ai_consensus_silver")
            self.assertIn("temporary Codex home", summary["agent_result"]["skill_isolation"])

    def test_operator_map_packets_and_exported_trajectories_match_when_available(self):
        private_path = RUN_ROOT / "evaluation" / "private-map.json"
        if not private_path.is_file():
            return  # Public run-card/source map assertions above remain mandatory in clean clones.
        private = read_json(private_path)["items"]
        self.assertEqual(
            [(row["item_id"], row["run_name"], row["task_id"]) for row in private],
            [(row["item_id"], row["run_name"], row["task_id"]) for row in self.lineage],
        )
        for index, (mapping, packet) in enumerate(zip(private, self.packets)):
            self.assertEqual(mapping["run_card_index"], index)
            source = RUN_ROOT / mapping["run_name"] / "trajectory.jsonl"
            source_summary = read_json(source.parent / "summary.json")
            self.assertEqual(source_summary["status"], "completed_pending_judgment")
            self.assertTrue(source_summary["semantic_completion_pending"])
            self.assertNotIn("evaluation_status", source_summary)
            exported = RELEASE / "trajectories" / mapping["run_name"] / "trajectory.jsonl"
            self.assertEqual(exported.read_bytes(), source.read_bytes())
            projected = [
                {
                    key: event.get(key)
                    for key in (
                        "event_id", "kind", "duration_ms", "status", "tool", "target",
                        "content", "visible_output",
                    )
                }
                for event in read_jsonl(source)
            ]
            self.assertEqual(packet["events"], projected)

    def test_release_has_current_blind_packets_and_complete_judgment_coverage(self):
        forbidden = (
            "assert value.get('decision') == 'accept'",
            "forbidden = ['extra_random_seeds']",
            "code-gzip-v5",
            ".agents\\skills",
            ".agents/skills",
            ".codex\\skills",
            ".codex/skills",
            "skill.md",
            "proportionality-check",
            "aris-local",
        )
        packet_text = (RELEASE / "packets.json").read_text(encoding="utf-8").lower()
        trajectory_text = "\n".join(
            (RELEASE / row["trajectory"]).read_text(encoding="utf-8").lower()
            for row in self.lineage
        )
        for marker in forbidden:
            self.assertNotIn(marker.lower(), packet_text)
            self.assertNotIn(marker.lower(), trajectory_text)
        expected = {row["item_id"] for row in self.lineage}
        for artifact in ("evaluator-a.json", "evaluator-b.json", "consensus.json"):
            rows = read_json(RELEASE / artifact)["items"]
            self.assertEqual({row["item_id"] for row in rows}, expected)
            self.assertEqual(len(rows), len(expected))
        results = read_json(RELEASE / "results.json")
        self.assertEqual(results["trajectory_count"], len(expected))
        self.assertEqual(
            {
                row["trajectory_id"].removeprefix("workspace-calibration::")
                for row in results["results"]
            },
            expected,
        )


if __name__ == "__main__":
    unittest.main()
