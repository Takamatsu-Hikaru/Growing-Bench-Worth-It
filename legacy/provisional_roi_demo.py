#!/usr/bin/env python3
"""LEGACY DEMO ONLY; use the canonical action-value scorer for benchmark results."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be in {low}..{high}")
    return result


def score(path: Path, budget_minutes: float) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    actions = source.get("atomic_actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"{path}: atomic_actions must be a non-empty array")
    rows = []
    action_total = 0.0
    for raw in actions:
        required = number(raw.get("required_for_task"), "required_for_task", 0, 4)
        outcome = number(raw.get("outcome_impact"), "outcome_impact", 0, 4)
        decision = number(raw.get("decision_impact"), "decision_impact", 0, 4)
        feasibility = number(raw.get("feasibility"), "feasibility", 0, 1)
        opportunity = number(raw.get("opportunity_cost"), "opportunity_cost", 0, 4)
        burden = number(raw.get("user_burden", 0), "user_burden", 0, 4)
        impact = max(outcome, decision)
        status = raw.get("status")
        observed = raw.get("observed_result")
        realized = 0.0
        if status == "completed" and observed == "helped":
            realized = impact * required / 4.0
        elif status == "completed" and observed == "uncertain":
            realized = impact * required / 4.0 * feasibility
        elif status not in {"completed", "failed", "reverted", "proposed", "deferred", "refused"}:
            raise ValueError(f"unsupported status {status!r}")
        action_cost = opportunity / 4.0 + burden / 4.0
        net = realized - action_cost
        action_total += net
        rows.append(
            {
                "action_id": raw["action_id"],
                "description": raw["description"],
                "status": status,
                "observed_result": observed,
                "necessity_weighted_realized_value": round(realized, 4),
                "opportunity_and_burden_cost": round(action_cost, 4),
                "net_before_time": round(net, 4),
                "cheaper_substitute_present": raw.get("cheaper_substitute") is not None,
            }
        )
    wall_seconds = number(source["task_outcome"].get("wall_seconds"), "wall_seconds", 0, 86400)
    wall_cost = wall_seconds / 60.0 / budget_minutes
    trajectory_value = action_total - wall_cost
    return {
        "schema_version": "workspace-provisional-roi-0.1",
        "task_id": source["task_id"],
        "source": str(path),
        "action_count": len(rows),
        "actual_wall_minutes": round(wall_seconds / 60.0, 4),
        "wall_budget_minutes": budget_minutes,
        "normalized_wall_cost": round(wall_cost, 4),
        "action_value_before_time": round(action_total, 4),
        "trajectory_value": round(trajectory_value, 4),
        "mean_value_per_action": round(trajectory_value / len(rows), 4),
        "nonpositive_action_count": sum(row["net_before_time"] <= 0 for row in rows),
        "actions_with_cheaper_substitute": sum(row["cheaper_substitute_present"] for row in rows),
        "actions": rows,
        "interpretation_boundary": "Ex-post small-sample diagnostic only. Uses observed result, necessity, impact, feasibility for uncertain results, opportunity cost, applicable burden, and total measured wall time. It is not a cross-task ranking or a substitute for timestamped per-action cost.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--budget-minutes", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.budget_minutes) or args.budget_minutes <= 0:
        raise ValueError("budget-minutes must be positive")
    result = {
        "schema_version": "workspace-provisional-roi-0.1",
        "results": [score(path, args.budget_minutes) for path in args.inputs],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({row["task_id"]: row["trajectory_value"] for row in result["results"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
