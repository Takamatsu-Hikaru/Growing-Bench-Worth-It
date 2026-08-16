from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "workspace-v0.2-calibration"
EVAL_ROOT = RUN_ROOT / "evaluation"
PUBLIC_ROOT = ROOT / "data" / "releases" / "workspace-v0.2-calibration"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def finalized_summary(summary: dict[str, Any], semantic_success: float, item_id: str) -> dict[str, Any]:
    value = json.loads(json.dumps(summary))
    value["execution_status"] = value.get("execution_status", value.get("status"))
    value["status"] = "completed_silver_judged"
    value["semantic_completion_pending"] = False
    value["evaluation_status"] = "ai_consensus_silver"
    value["judgment_artifact"] = f"consensus.json#{item_id}"
    for criterion in value.get("criterion_results", []):
        if criterion.get("kind") == "semantic":
            criterion["status"] = "passed" if semantic_success == 1 else "partial" if semantic_success == 0.5 else "failed"
    artifacts = value.get("artifacts", {})
    for key in ("raw_stderr", "raw_stdout", "agent_events"):
        artifacts.pop(key, None)
    agent_result = value.get("agent_result", {})
    agent_result["executor_contract"] = "codex-read-only-proposal-plus-allowed-host-executor"
    agent_result["skill_isolation"] = "temporary Codex home; discovered user/plugin SKILL.md entries disabled"
    for key in ("stderr", "stdout", "events", "prompt"):
        agent_result.get("artifacts", {}).pop(key, None)
    return value


def validate_lineage(card: dict[str, Any], private: dict[str, Any], packets: dict[str, Any]) -> None:
    card_rows = card.get("runs")
    private_rows = private.get("items")
    packet_rows = packets.get("items")
    if not all(isinstance(rows, list) and len(rows) == 8 for rows in (card_rows, private_rows, packet_rows)):
        raise ValueError("run card, private map, and packets must each contain eight rows")
    packet_ids = [row["item_id"] for row in packet_rows]
    if packet_ids != [row["item_id"] for row in private_rows]:
        raise ValueError("packet/private-map item order differs")
    for index, (card_row, private_row) in enumerate(zip(card_rows, private_rows)):
        if private_row.get("run_card_index") != index:
            raise ValueError(f"private-map run_card_index mismatch at {index}")
        if (card_row.get("run"), card_row.get("task_id")) != (private_row.get("run_name"), private_row.get("task_id")):
            raise ValueError(f"run-card/private-map source mismatch at {index}")
        if not str(card_row.get("run", "")).endswith("-rc1"):
            raise ValueError(f"non-RC1 source run: {card_row.get('run')}")
        source = RUN_ROOT / card_row["run"]
        task = read(source / "task.json")
        if task["task_id"] != card_row["task_id"]:
            raise ValueError(f"source task mismatch: {card_row['run']}")
        trajectory = (source / "trajectory.jsonl").read_text(encoding="utf-8")
        forbidden = (".agents\\skills", ".agents/skills", ".codex\\skills", ".codex/skills", "SKILL.md")
        if any(marker.casefold() in trajectory.casefold() for marker in forbidden):
            raise ValueError(f"user skill leaked into trajectory: {card_row['run']}")
    packet_text = json.dumps(packets, ensure_ascii=False)
    old_markers = (
        "code-gzip-v5", '"run_name": "internal-deterministic"',
        "assert value.get('decision') == 'accept'", "forbidden = ['extra_random_seeds']",
    )
    if any(marker in packet_text for marker in old_markers):
        raise ValueError("packet contains an old source-run or semantic-oracle marker")


def main() -> int:
    card = read(RUN_ROOT / "slice.run-card.json")
    private = read(EVAL_ROOT / "private-map.json")
    packets = read(EVAL_ROOT / "packets.json")
    consensus = {row["item_id"]: row for row in read(EVAL_ROOT / "consensus.json")["items"]}
    validate_lineage(card, private, packets)

    with tempfile.TemporaryDirectory(prefix="growing-bench-export-", dir=RUN_ROOT) as temp_name:
        staging = Path(temp_name) / "workspace-v0.2-calibration"
        staging.mkdir()
        for name in (
            "packets.json", "evaluator-a.json", "evaluator-b.json", "consensus.json",
            "results.json", "report.html",
        ):
            shutil.copy2(EVAL_ROOT / name, staging / name)
        shutil.copytree(EVAL_ROOT / "bundles", staging / "bundles")

        public_map = {"schema_version": "growing-bench-source-run-map-1.0", "items": []}
        for row in private["items"]:
            item_id, run_name = row["item_id"], row["run_name"]
            source = RUN_ROOT / run_name
            target = staging / "trajectories" / run_name
            target.mkdir(parents=True)
            for source_name, target_name in (
                ("trajectory.jsonl", "trajectory.jsonl"),
                ("changes.diff", "changes.diff"),
                ("agent/final.md", "final.md"),
            ):
                if (source / source_name).is_file():
                    shutil.copy2(source / source_name, target / target_name)
            summary = finalized_summary(
                read(source / "summary.json"), float(consensus[item_id]["semantic_success"]), item_id,
            )
            write(target / "summary.json", summary)
            public_map["items"].append({
                "item_id": item_id, "run_name": run_name, "task_id": row["task_id"],
                "trajectory": f"trajectories/{run_name}/trajectory.jsonl",
            })

        card["status"] = "completed_silver_judged"
        card["release"] = "0.2.0-rc1"
        card["source_mapping"] = "slice.run-card.json -> private-map.json -> packets.json -> public source-run-map.json"
        card["agent_isolation"] = "temporary Codex home with every discovered user/plugin SKILL.md disabled"
        for row in card["runs"]:
            row["status"] = "completed_silver_judged"
        write(RUN_ROOT / "slice.run-card.json", card)
        write(staging / "run-card.json", card)
        write(staging / "source-run-map.json", public_map)
        results = read(EVAL_ROOT / "results.json")
        write(staging / "evaluation-method.json", {
            "schema_version": "growing-bench-evaluation-method-1.1",
            "packet_set_id": "workspace-v0.2-calibration-rc1-source-map-fix",
            "task_count": 8,
            "executor": "codex-read-only-proposal-plus-allowed-host-executor",
            "agent_isolation": "temporary Codex home; all discovered user/plugin SKILL.md entries disabled; plugin features disabled",
            "blind_evaluators": [
                {"role": "evaluator-a", "model": "gpt-5.6-sol", "artifact": "evaluator-a.json"},
                {"role": "evaluator-b", "model": "gpt-5.6-terra", "artifact": "evaluator-b.json"},
                {"role": "adjudicator-c", "model": "gpt-5.6-sol", "artifact": "consensus.json"},
            ],
            "judge_isolation": "same temporary-home and disabled-skill contract as the Agent runs",
            "reference_status": "ai_consensus_silver",
            "scoring_status": "deterministic_silver_diagnostic_with_imputed_priors",
            "scoring_assumptions": results["scoring_evidence_boundary"],
            "full_model_matrix": False,
            "raw_logs_published": False,
        })

        backup = RUN_ROOT / "public-release-pre-source-map-fix"
        if backup.exists():
            raise RuntimeError(f"release backup already exists: {backup}")
        if PUBLIC_ROOT.exists():
            shutil.move(str(PUBLIC_ROOT), str(backup))
        shutil.move(str(staging), str(PUBLIC_ROOT))

    print(json.dumps({"export": str(PUBLIC_ROOT), "trajectory_count": 8, "all_source_runs_rc1": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
