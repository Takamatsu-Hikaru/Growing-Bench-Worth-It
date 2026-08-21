from __future__ import annotations

import html
import json
import shutil
import webbrowser
from pathlib import Path
from typing import Any

from .interactive import load_scenario, run_interactive_scenario
from .interactive_judging import PROMPT_VERSION as INTERACTION_PROMPT_VERSION, run_interaction_judgment
from .judging import JUDGE_PROMPT_VERSION, build_packet, score_judgment
from .self_test import _decorate_score, _judge_one
from .task_contract import load_task


INTERACTIVE_SUITES = {
    "quick": (
        "code-reuse-helper-present.json", "writing-fixed-set.json",
        "review-deterministic.json", "peer-extra-data-irrelevant.json",
    ),
    "balanced": (
        "code-reuse-helper-present.json", "code-reuse-helper-absent.json",
        "writing-fixed-set.json", "writing-sample.json",
        "review-deterministic.json", "review-stochastic.json",
        "peer-extra-data-irrelevant.json", "peer-causal-intervention.json",
    ),
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def suite_scenarios(name: str, explicit: list[Path] | None = None) -> list[Path]:
    if explicit:
        rows = [path.resolve() for path in explicit]
        for path in rows:
            load_scenario(path)
        return rows
    if name not in INTERACTIVE_SUITES:
        raise ValueError(f"unknown interactive suite {name!r}; choose from {sorted(INTERACTIVE_SUITES)}")
    root = Path(__file__).resolve().parent / "resources" / "interactive"
    return [root / name for name in INTERACTIVE_SUITES[name]]


def _condition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        return None if not values else sum(values) / len(values)
    return {
        "run_count": len(rows), "task_success": mean("task_success"),
        "necessary_action_recall": mean("necessary_action_recall"),
        "trajectory_roi": mean("trajectory_roi"), "state_update_success": mean("state_update_success"),
        "foreground_precision": mean("foreground_precision"),
        "unnecessary_claim_rate": mean("unnecessary_claim_rate"),
        "stale_narrative_events": sum(int(row["stale_narrative_events"]) for row in rows),
        "scenario_correction_turn_count": sum(int(row["scenario_pressure"]["correction_turn_count"]) for row in rows),
        "scenario_takeover_count": sum(bool(row["scenario_pressure"]["takeover_planned"]) for row in rows),
        "scenario_pressure_points": sum(float(row["scenario_pressure"]["pressure_points"]) for row in rows),
        "observed_agent_burden_points": sum(float(row["observed_agent_burden_points"]) for row in rows),
        "observed_elapsed_seconds": sum(float(row.get("observed", {}).get("elapsed_seconds", 0)) for row in rows),
    }


def _pct(value: Any) -> str:
    return "n/a" if value is None else f"{100 * float(value):.0f}%"


def render_interactive_report(result: dict[str, Any], output: Path) -> Path:
    baseline, intervention = result["summary"]["baseline"], result["summary"]["intervention"]
    cards = [
        ("Task success", _pct(baseline["task_success"]), _pct(intervention["task_success"])),
        ("State update success", _pct(baseline["state_update_success"]), _pct(intervention["state_update_success"])),
        ("Necessary-action recall", _pct(baseline["necessary_action_recall"]), _pct(intervention["necessary_action_recall"])),
        ("Stale narrative events", str(baseline["stale_narrative_events"]), str(intervention["stale_narrative_events"])),
        ("Scenario pressure", f"{baseline['scenario_pressure_points']:.1f}", f"{intervention['scenario_pressure_points']:.1f}"),
        ("Observed Agent burden", f"{baseline['observed_agent_burden_points']:.1f}", f"{intervention['observed_agent_burden_points']:.1f}"),
    ]
    card_html = "".join(f'<div class="card"><b>{html.escape(a)} → {html.escape(b)}</b><span>{html.escape(label)}</span></div>' for label, a, b in cards)
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in result["results"]:
        grouped.setdefault(row["scenario_id"], {})[row["condition"]] = row
    sections = []
    for scenario_id, conditions in grouped.items():
        columns = []
        for condition in ("baseline", "intervention"):
            row = conditions.get(condition)
            if not row:
                columns.append(f'<div class="column"><h3>{condition.title()}</h3><p>Run unavailable.</p></div>')
                continue
            signals = "".join(
                f'<li><b>{html.escape(signal["signal_id"])}</b> · {html.escape(signal["status"])}<br>{html.escape(signal["explanation"])}</li>'
                for signal in row["interaction_judgment"]["signals"]
            )
            spans = "".join(
                f'<li><span class="pill {html.escape(span["label"])}">{html.escape(span["label"])}</span>{html.escape(span["quote"])}</li>'
                for span in row["interaction_judgment"]["spans"]
            ) or "<li>No interaction span was labeled.</li>"
            columns.append(
                f'<div class="column"><h3>{condition.title()}</h3>'
                f'<p>Success {_pct(row["task_success"])} · action recall {_pct(row["necessary_action_recall"])} · state update {_pct(row["state_update_success"])}</p>'
                f'<p class="meta">ROI {row["trajectory_roi"] if row["trajectory_roi"] is not None else "n/a"} · stale {row["stale_narrative_events"]} · scenario pressure {row["scenario_pressure"]["pressure_points"]} · observed Agent burden {row["observed_agent_burden_points"]}</p>'
                f'<details><summary>User signals</summary><ul>{signals}</ul></details>'
                f'<details><summary>Visible narrative spans</summary><ul>{spans}</ul></details>'
                f'<p><a href="{html.escape(row["trajectory_path"])}">Open recorded trajectory</a></p></div>'
            )
        sections.append(f'<section><h2>{html.escape(scenario_id)}</h2><div class="pair">{"".join(columns)}</div></section>')
    css = "body{margin:0;background:#f5f7fb;color:#102a43;font:15px/1.5 system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:36px 20px 70px}h1{font-size:38px}.lede,.meta{color:#60758a}.cards,.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.cards{grid-template-columns:repeat(3,minmax(0,1fr))}.card,.column,section{background:#fff;border:1px solid #dce5ef;border-radius:14px;padding:18px}.card b,.card span{display:block}.card span{color:#60758a}section{margin-top:18px}.column{background:#fbfdff}li{margin:8px 0}.pill{border-radius:999px;background:#eaf2ff;padding:2px 7px;margin-right:7px;font-size:11px}@media(max-width:760px){.cards,.pair{grid-template-columns:1fr}}"
    document = f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Growing Bench interactive report</title><style>{css}</style></head><body><main class="wrap"><h1>Did the Agent update with the user?</h1><p class="lede">Real workspace work across a controlled multi-turn interaction. Scenario-authored pressure is shown separately from burden caused by observed Agent behavior.</p><div class="cards">{card_html}</div>{"".join(sections)}</main></body></html>'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return output


def run_interactive_self_test(
    intervention: Path, output: Path, *, suite: str = "quick",
    scenario_paths: list[Path] | None = None, agent: str = "codex", judge: str = "codex",
    model: str | None = None, judge_model: str | None = None, reasoning: str = "high",
    judge_reasoning: str = "high", timeout: float = 1200,
    command_template: str | None = None, judge_command_template: str | None = None,
    strict: bool = False, allow_partial: bool = False, open_report: bool = True,
    user_mode: str = "scripted", user_agent: str = "codex", user_model: str | None = None,
    user_reasoning: str = "medium", user_command_template: str | None = None,
) -> dict[str, Any]:
    intervention, output = intervention.resolve(), output.resolve()
    if not intervention.is_file():
        raise FileNotFoundError(f"intervention file is missing: {intervention}")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    scenarios = suite_scenarios(suite, scenario_paths)
    output.mkdir(parents=True)
    shutil.copy2(intervention, output / "intervention.md")
    run_card = {
        "schema_version": "growing-bench-interactive-self-test-run-card-1.0", "suite": suite,
        "scenario_ids": [load_scenario(path)["scenario_id"] for path in scenarios],
        "agent": {"adapter": agent, "model": model, "reasoning": reasoning},
        "user": {"mode": user_mode, "adapter": None if user_mode == "scripted" else user_agent, "model": user_model},
        "judges": {"adapter": judge, "model": judge_model, "action_prompt": JUDGE_PROMPT_VERSION,
                   "interaction_prompt": INTERACTION_PROMPT_VERSION, "strict": strict, "condition_blind": True},
    }
    _write_json(output / "run-card.json", run_card)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for scenario_path in scenarios:
        scenario = load_scenario(scenario_path)
        for condition in ("baseline", "intervention"):
            run_name = f"{scenario['scenario_id']}--{condition}"
            run_dir = output / "runs" / run_name
            try:
                summary = run_interactive_scenario(
                    scenario_path, run_dir, agent=agent, model=model, reasoning=reasoning,
                    timeout=timeout, intervention=intervention if condition == "intervention" else None,
                    command_template=command_template, user_mode=user_mode, user_agent=user_agent,
                    user_model=user_model, user_reasoning=user_reasoning,
                    user_command_template=user_command_template,
                )
                if summary["status"] not in {"completed", "completed_pending_judgment"}:
                    raise ValueError(f"agent run ended with {summary['status']}")
                action_dir = output / "judgments" / run_name / "actions"
                action_judgment, agreement = _judge_one(
                    run_dir, action_dir, judge, judge_model, judge_reasoning, timeout,
                    judge_command_template, strict,
                )
                task = load_task(run_dir / "task.json")
                score, bundle = score_judgment(task, build_packet(run_dir), action_judgment, f"interactive::{run_name}")
                _write_json(action_dir / "bundle.json", bundle)
                summary_for_score = {**summary, "run_dir": str(run_dir)}
                score = _decorate_score(score, summary_for_score, action_judgment, agreement, run_name, condition)
                score["trajectory_roi"] = None if score["selected_action_cost"] <= 0 else score["trajectory_value"] / score["selected_action_cost"]
                interaction = run_interaction_judgment(
                    run_dir, output / "judgments" / run_name / "interaction", judge=judge,
                    model=judge_model, reasoning=judge_reasoning, timeout=timeout,
                    command_template=judge_command_template, strict=strict,
                )
                row = {**score, **interaction["score"], "run_name": run_name,
                       "scenario_id": scenario["scenario_id"], "condition": condition,
                       "interaction_judgment": interaction["judgment"],
                       "trajectory_path": str((run_dir / "trajectory.jsonl").resolve())}
                results.append(row)
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
                failures.append({"run": run_name, "status": str(exc)})
                if not allow_partial:
                    continue
    expected = 2 * len(scenarios)
    status = "completed" if not failures and len(results) == expected else "partial_failed"
    baseline = [row for row in results if row["condition"] == "baseline"]
    intervention_rows = [row for row in results if row["condition"] == "intervention"]
    result = {
        "schema_version": "growing-bench-interactive-self-test-results-1.0", "status": status,
        "suite": suite, "strict": strict, "results": results, "failures": failures,
        "summary": {"baseline": _condition_summary(baseline), "intervention": _condition_summary(intervention_rows)},
    }
    _write_json(output / "results.json", result)
    report = render_interactive_report(result, output / "report.html")
    result["report"] = str(report)
    _write_json(output / "results.json", result)
    if open_report:
        try:
            webbrowser.open(report.as_uri())
        except OSError:
            pass
    return result
