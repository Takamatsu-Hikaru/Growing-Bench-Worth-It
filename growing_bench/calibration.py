from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .agents import run_agent
from .judging import (
    JUDGE_PROMPT_VERSION,
    JUDGMENT_SCHEMA_VERSION,
    extract_json,
    judge_prompt,
    validate_judgment,
)


DEFAULT_CASES = Path(__file__).resolve().parent / "resources" / "calibration" / "necessary_gate_cases.json"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _packet(case: dict[str, Any]) -> dict[str, Any]:
    missed = case["label"] == "missed"
    requirement_id = case.get("requirement_id") or "C1"
    criteria = [
        {
            "criterion_id": requirement_id,
            "description": case.get("criterion", "Complete the bounded target behavior."),
            "kind": "semantic",
            "weight": 1.0,
        }
    ]
    return {
        "schema_version": "growing-bench-blind-run-packet-1.0",
        "task": {
            "title": case["case_id"],
            "kind": case.get("kind", "code"),
            "prompt": case.get("task_prompt", "Complete the bounded target with proportionate work."),
            "authorization": "Modify only the declared target.",
            "completion_criteria": criteria,
            "allowed_paths": ["target"],
            "budget": {"human_minutes": 45, "machine_minutes": 10, "compute_cost": 1},
        },
        "verified_outcome": {
            "status": "failed" if missed else "completed_pending_judgment",
            "post_checks_passed": not missed,
            "allowed_paths_ok": True,
            "machine_completion_passed": not missed,
            "criterion_results": [],
            "elapsed_seconds": 1,
            "changed_paths": [] if missed else ["target"],
            "usage": None,
        },
        "events": [] if missed else [
            {
                "event_id": "event-1",
                "kind": case.get("event_kind", "tool_result"),
                "status": case.get("event_status", "success"),
                "duration_ms": int(case.get("duration_ms", 1000)),
                "content": "Completed action: " + case["description"],
            }
        ],
    }


def _judgment(case: dict[str, Any]) -> dict[str, Any]:
    if case["label"] == "missed":
        actions = []
        missed = [
            {
                "description": case["description"],
                "requirement_id": case["requirement_id"],
                "omission_consequence": case["omission_consequence"],
                "evidence_refs": [],
                "confidence": 0.9,
            }
        ]
    else:
        actions = [
            {
                "action_id": "A1",
                "description": case["description"],
                "action_type": "verification",
                "status": "reverted" if case["case_id"] == "failed-and-reverted" else "completed",
                "label": case["label"],
                "atomic": case.get("atomic", True),
                "requirement_id": case.get("requirement_id"),
                "omission_consequence": case.get("omission_consequence"),
                "evidence_refs": ["event-1"],
                "explanation": "Calibration action with an explicit decision boundary.",
                "cheaper_substitute": case.get("cheaper_substitute"),
                "estimated_machine_minutes": case.get("estimated_machine_minutes"),
                "confidence": 0.9,
            }
        ]
        missed = []
    return {
        "schema_version": JUDGMENT_SCHEMA_VERSION,
        "evaluator_id": "calibration-fixture",
        "semantic_success": 1.0,
        "confidence": 0.9,
        "actions": actions,
        "missed_actions": missed,
    }


def _actual_label(judged: dict[str, Any], expected: str) -> str:
    if expected == "missed":
        return "missed" if len(judged["missed_actions"]) == 1 and not judged["actions"] else "invalid_missed_shape"
    labels = [row["label"] for row in judged["actions"]]
    return labels[0] if len(labels) == 1 else f"invalid_action_count:{len(labels)}"


def run_gate_calibration(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    """Validate the deterministic contract against the frozen decision boundaries."""

    source = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for case in source["cases"]:
        judged = validate_judgment(_judgment(case), _packet(case))
        actual = _actual_label(judged, case["expected"])
        rows.append(
            {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "expected": case["expected"],
                "actual": actual,
                "passed": actual == case["expected"],
            }
        )
    return {
        "schema_version": "growing-bench-judge-calibration-results-1.0",
        "mode": "contract",
        "prompt_version": JUDGE_PROMPT_VERSION,
        "case_count": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "cases": rows,
    }


def run_live_calibration(
    output: Path,
    *,
    judge: str = "codex",
    model: str | None = None,
    reasoning: str = "high",
    timeout: float = 1200,
    command_template: str | None = None,
    path: Path = DEFAULT_CASES,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run the current LLM judge prompt on every frozen calibration action."""

    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"calibration output already exists: {output}")
    output.mkdir(parents=True)
    source = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    selected = source["cases"]
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case["case_id"] in wanted]
        missing = wanted - {case["case_id"] for case in selected}
        if missing:
            raise ValueError(f"unknown calibration case(s): {', '.join(sorted(missing))}")
    for case in selected:
        live_expected = case.get("live_expected", case["expected"])
        packet = _packet(case)
        case_dir = output / case["case_id"]
        _write_json(case_dir / "packet.json", packet)
        prompt = judge_prompt(packet, f"calibration::{case['case_id']}")
        with tempfile.TemporaryDirectory(prefix="growing-bench-calibration-") as name:
            agent_result = run_agent(
                judge,
                prompt,
                Path(name),
                case_dir / "judge",
                model=model,
                reasoning=reasoning,
                timeout=timeout,
                command_template=command_template,
            )
        if agent_result["status"] != "completed":
            rows.append(
                {
                    "case_id": case["case_id"],
                    "pair_id": case["pair_id"],
                    "expected": live_expected,
                    "actual": "judge_failed",
                    "passed": False,
                }
            )
            continue
        final = (case_dir / "judge" / "final.md").read_text(encoding="utf-8")
        try:
            judged = validate_judgment(extract_json(final), packet)
            _write_json(case_dir / "judgment.json", judged)
            actual = _actual_label(judged, live_expected)
        except (ValueError, json.JSONDecodeError) as exc:
            actual = f"invalid:{exc}"
        rows.append(
            {
                "case_id": case["case_id"],
                "pair_id": case["pair_id"],
                "expected": live_expected,
                "actual": actual,
                "passed": actual == live_expected,
            }
        )
    result = {
        "schema_version": "growing-bench-judge-calibration-results-1.0",
        "mode": "live_llm",
        "prompt_version": JUDGE_PROMPT_VERSION,
        "judge": {"adapter": judge, "model": model, "reasoning": reasoning},
        "case_count": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "cases": rows,
    }
    _write_json(output / "results.json", result)
    return result
