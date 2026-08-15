from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluation import assemble, score as scorer


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_rows(path: Path, values: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _ratio(value: float, cost: float) -> float | None:
    return None if cost <= scorer.EPSILON else value / cost


def score_frozen_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    prebundles = _rows(run_dir / "preannotation_bundles.jsonl")
    packets = _rows(run_dir / "annotation_packets.jsonl")
    silver = json.loads((run_dir / "dimension.silver.json").read_text(encoding="utf-8"))
    scores: list[dict[str, Any]] = []
    bundle_dir = run_dir / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for row in prebundles:
        base = row["bundle"]
        action_ids = {action["action_id"] for action in base["actions"]}
        gold = {
            "reference_type": silver["reference_type"],
            "items": [item for item in silver["items"] if item["action_id"] in action_ids],
        }
        packet_ids = {item["packet_id"] for item in gold["items"]}
        packet_subset = [packet for packet in packets if packet["packet_id"] in packet_ids]
        bundle = assemble.assemble_bundle(base["task"], base["trajectory"], base["actions"], gold, packet_subset, None)
        value = scorer.score_bundle(bundle)
        selected = [action for action in bundle["actions"] if action["selected_by_agent"]]
        annotations = {item["action_id"]: item for item in bundle["annotations"]}
        action_scores = {item["action_id"]: item for item in value["actions"]}
        unnecessary = [
            action for action in selected
            if annotations[action["action_id"]]["required_for_task"] < 2
            and action_scores[action["action_id"]]["net_action_value"] < 0
        ]
        value["unnecessary_action_count"] = len(unnecessary)
        value["unnecessary_action_rate"] = len(unnecessary) / len(selected) if selected else 0.0
        value["missed_required_action_rate"] = None if value["necessary_action_recall"] is None else 1.0 - value["necessary_action_recall"]
        value["trajectory_roi"] = _ratio(value["trajectory_value"], value["selected_action_cost"])
        value["intervention_id"] = base["trajectory"]["intervention_id"]
        scores.append(value)
        (bundle_dir / f"{row['trajectory_id'].replace(':', '_')}.json").write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if not scores:
        raise ValueError("frozen run has no trajectories")
    _write_rows(run_dir / "scores.jsonl", scores)
    total_value = sum(row["trajectory_value"] for row in scores)
    total_cost = sum(row["selected_action_cost"] for row in scores)
    recalls = [row["necessary_action_recall"] for row in scores if row["necessary_action_recall"] is not None]
    missed = [row["missed_required_action_rate"] for row in scores if row["missed_required_action_rate"] is not None]
    result = {
        "schema_version": "growing-bench-smoke-results-1.1",
        "trajectory_count": len(scores),
        "mean_task_success": sum(row["task_success"] for row in scores) / len(scores),
        "mean_necessary_action_recall": sum(recalls) / len(recalls),
        "mean_unnecessary_action_rate": sum(row["unnecessary_action_rate"] for row in scores) / len(scores),
        "mean_missed_required_action_rate": sum(missed) / len(missed),
        "total_avoidable_human_minutes": sum(row["avoidable_human_minutes"] for row in scores),
        "mean_trajectory_value": total_value / len(scores),
        "total_trajectory_value": total_value,
        "total_selected_action_cost": total_cost,
        "portfolio_roi": _ratio(total_value, total_cost),
        "roi_aggregation": "sum(trajectory_value) / sum(selected_action_cost); per-trajectory ratios are diagnostic only",
        "reference_type": "ai_consensus_silver",
        "human_gold": False,
    }
    (run_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result

