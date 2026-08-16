from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "workspace-v0.2-calibration"
EVAL_ROOT = RUN_ROOT / "evaluation"
RUN_CARD = RUN_ROOT / "slice.run-card.json"

CATEGORIES = {
    "necessary_efficient", "necessary_expensive", "avoidable", "optional_conditional",
    "proposed_not_executed", "failed_reverted", "unresolved",
}
ACTION_TYPES = {"analysis", "edit", "implementation", "verification", "decision", "communication", "other"}
STATUSES = {"proposed", "started", "completed", "failed", "reverted"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def workspace_evidence(run: Path) -> dict[str, str]:
    value = {}
    for relative in ("README.md", "main.tex", "evidence.json", "data/results.json"):
        path = run / "before" / relative
        if path.is_file():
            value[relative] = path.read_text(encoding="utf-8")
    return value


def prepare() -> dict[str, Any]:
    items, private = [], []
    card = read_json(RUN_CARD)
    run_rows = card.get("runs")
    if not isinstance(run_rows, list) or len(run_rows) != card.get("task_count"):
        raise ValueError("slice.run-card.json has inconsistent task_count/runs")
    run_names = [row.get("run") for row in run_rows]
    task_ids = [row.get("task_id") for row in run_rows]
    if any(not isinstance(name, str) or not name.endswith("-rc1") for name in run_names):
        raise ValueError("every RC1 calibration source run must end with -rc1")
    if len(set(run_names)) != len(run_names) or len(set(task_ids)) != len(task_ids):
        raise ValueError("slice.run-card.json contains duplicate run or task identifiers")
    for index, card_row in enumerate(run_rows, start=1):
        run_name = card_row["run"]
        run = RUN_ROOT / run_name
        task = read_json(run / "task.json")
        if task["task_id"] != card_row["task_id"]:
            raise ValueError(f"run-card task mismatch for {run_name}")
        summary = read_json(run / "summary.json")
        events = []
        for event in read_jsonl(run / "trajectory.jsonl"):
            events.append({key: event.get(key) for key in (
                "event_id", "kind", "duration_ms", "status", "tool", "target",
                "content", "visible_output",
            )})
        item_id = f"workspace-calibration-{index:02d}"
        items.append({
            "item_id": item_id,
            "task": {
                "title": task["title"], "kind": task["kind"], "prompt": task["prompt"],
                "completion_criteria": task["completion_criteria"],
                "allowed_paths": task["allowed_paths"], "matched_group": task["matched_group"],
            },
            "workspace_evidence": workspace_evidence(run), "events": events,
            "changed_paths": summary["changes"]["changed_paths"],
            "diff": (run / "changes.diff").read_text(encoding="utf-8"),
            "verified_outcome": {
                "post_checks_passed": summary["post_checks_passed"],
                "allowed_paths_ok": summary["allowed_paths_ok"],
                "machine_completion_passed": summary["machine_completion_passed"],
                "criterion_results": summary["criterion_results"],
                "trajectory_elapsed_seconds": summary["elapsed_seconds"],
            },
        })
        private.append({"item_id": item_id, "run_name": run_name, "task_id": task["task_id"], "run_card_index": index - 1})
    write_json(EVAL_ROOT / "packets.json", {
        "schema_version": "growing-bench-workspace-eval-packet-1.0",
        "blinding": "model and intervention identities omitted", "items": items,
    })
    write_json(EVAL_ROOT / "private-map.json", {"items": private})
    return {"item_count": len(items), "packets": str(EVAL_ROOT / "packets.json")}


def response_shape() -> str:
    return (
        '{"items":[{"item_id":"...","semantic_success":0|0.5|1,'
        '"actions":[{"description":"one independently choosable action",'
        '"action_type":"analysis|edit|implementation|verification|decision|communication|other",'
        '"status":"proposed|started|completed|failed|reverted",'
        '"category":"necessary_efficient|necessary_expensive|avoidable|optional_conditional|proposed_not_executed|failed_reverted|unresolved",'
        '"evidence_event_ids":["exact event id"],"required_level":0|1|2|3|4,'
        '"outcome_impact":0|1|2|3|4,"decision_impact":0|1|2|3|4,'
        '"opportunity_cost":0|1|2|3|4,"user_burden":0|1|2|3|4|null,'
        '"cheaper_substitute":null|{"description":"...","cost_fraction":0.0,"comparable_benefit":true}}],'
        '"missed_actions":[{"description":"required action absent from trajectory",'
        '"criterion_id":"exact criterion id","required_level":3|4,'
        '"outcome_impact":1|2|3|4,"decision_impact":0|1|2|3|4}],'
        '"confidence":0.0,"notes":""}]}'
    )


def prompt(adjudicate: bool) -> str:
    opening = (
        "You are the third blind adjudicator. Read packets.json, evaluator-a.json, and evaluator-b.json. "
        "Merge only semantic duplicates and preserve genuine disagreement as unresolved. "
        if adjudicate else
        "You are an independent blind evaluator. Read packets.json and judge the visible workspace trajectories. "
    )
    return opening + (
        "You cannot see model or intervention identity. Identify 1-6 independently choosable actions per item, "
        "not every command or sentence. Cite exact visible event IDs. Necessary-but-expensive is not avoidable. "
        "Avoidable requires a cheaper path with comparable outcome. Proposed-but-not-executed carries no actual "
        "execution cost. External peer review user_burden must be null. Do not output ROI or infer hidden reasoning. "
        "Return JSON only with exactly one row for every packet using this shape: " + response_shape()
    )


def extract_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines(); value = "\n".join(lines[1:-1])
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("judge returned no JSON object")
        result = json.loads(value[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("judge response must be an object")
    return result


def validate_response(value: dict[str, Any]) -> None:
    packets = {row["item_id"]: row for row in read_json(EVAL_ROOT / "packets.json")["items"]}
    rows = value.get("items")
    if not isinstance(rows, list) or {row.get("item_id") for row in rows} != set(packets):
        raise ValueError("judge item coverage mismatch")
    for row in rows:
        if row.get("semantic_success") not in {0, 0.5, 1}:
            raise ValueError("invalid semantic_success")
        actions = row.get("actions")
        if not isinstance(actions, list) or not 1 <= len(actions) <= 6:
            raise ValueError("each item requires 1-6 actions")
        event_ids = {event["event_id"] for event in packets[row["item_id"]]["events"]}
        for action in actions:
            if action.get("action_type") not in ACTION_TYPES or action.get("status") not in STATUSES or action.get("category") not in CATEGORIES:
                raise ValueError("invalid action enum")
            refs = action.get("evidence_event_ids")
            if not isinstance(refs, list) or not refs or not set(refs).issubset(event_ids):
                raise ValueError("invalid action evidence")
        if not isinstance(row.get("missed_actions", []), list):
            raise ValueError("missed_actions must be an array")


def call_judge(label: str, model: str, adjudicate: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "workspace_judge_runner.py"),
        "--label", label,
        "--model", model,
    ]
    if adjudicate:
        command.append("--adjudicate")
    completed = subprocess.run(
        command, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=1200, check=False, cwd=ROOT,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"judge {label} failed: {completed.stderr.strip()}")
    value = read_json(EVAL_ROOT / f"{label}.json")
    validate_response(value)
    return {"label": label, "model": model, "item_count": len(value["items"])}

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    judge = sub.add_parser("judge")
    judge.add_argument("--label", required=True); judge.add_argument("--model", required=True)
    judge.add_argument("--adjudicate", action="store_true")
    args = parser.parse_args()
    value = prepare() if args.command == "prepare" else call_judge(args.label, args.model, args.adjudicate)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
