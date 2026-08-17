from __future__ import annotations

import html
import json
import shutil
import tempfile
import webbrowser
from pathlib import Path
from typing import Any

from .agents import run_agent
from .execution import run_task
from .judging import (
    JUDGE_PROMPT_VERSION,
    JUDGMENT_SCHEMA_VERSION,
    adjudication_prompt,
    agreement_summary,
    build_packet,
    extract_json,
    judge_prompt,
    score_judgment,
    validate_judgment,
)
from .paths import REPOSITORY_ROOT
from .quality import trajectory_completeness
from .task_contract import load_task


SUITES = {
    "quick": (
        "workspace-v0.2--code-reuse--compatible-tested-helper-present",
        "workspace-v0.2--writing-hedges--complete-fixed-set-observation",
        "workspace-v0.2--review-seeds--deterministic-execution",
        "workspace-v0.2--review-extra-experiment--irrelevant-extra-dataset",
    ),
    "balanced": (
        "workspace-v0.2--code-reuse--compatible-tested-helper-present",
        "workspace-v0.2--code-reuse--compatible-helper-absent",
        "workspace-v0.2--writing-hedges--complete-fixed-set-observation",
        "workspace-v0.2--writing-hedges--sample-based-population-estimate",
        "workspace-v0.2--review-seeds--deterministic-execution",
        "workspace-v0.2--review-seeds--stochastic-execution",
        "workspace-v0.2--review-extra-experiment--irrelevant-extra-dataset",
        "workspace-v0.2--review-mechanism--causal-intervention",
    ),
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _task_path(task_id: str) -> Path:
    repository = REPOSITORY_ROOT / "tracks" / "workspace-v0.2" / "tasks" / task_id / "task.json"
    if repository.is_file():
        return repository
    packaged = Path(__file__).resolve().parent / "resources" / "suites" / "workspace-v0.2" / task_id / "task.json"
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(f"suite task is unavailable: {task_id}")


def suite_tasks(name: str, explicit: list[Path] | None = None) -> list[Path]:
    if explicit:
        rows = [path.resolve() for path in explicit]
        for path in rows:
            load_task(path)
        return rows
    if name not in SUITES:
        raise ValueError(f"unknown suite {name!r}; choose from {sorted(SUITES)}")
    return [_task_path(task_id) for task_id in SUITES[name]]


def _call_judge(
    packet: dict[str, Any], prompt: str, output: Path, judge: str, model: str | None,
    reasoning: str, timeout: float, command_template: str | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="growing-bench-judge-") as name:
        workspace = Path(name)
        result = run_agent(
            judge, prompt, workspace, output, model=model, reasoning=reasoning,
            timeout=timeout, command_template=command_template,
        )
    if result["status"] != "completed":
        raise ValueError(f"judge failed with status {result['status']}")
    final = (output / "final.md").read_text(encoding="utf-8")
    return validate_judgment(extract_json(final), packet)


def _judge_one(
    run_dir: Path, output: Path, judge: str, model: str | None, reasoning: str,
    timeout: float, command_template: str | None, strict: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = build_packet(run_dir)
    _write_json(output / "packet.json", packet)
    a = _call_judge(
        packet, judge_prompt(packet, "evaluator-a"), output / "evaluator-a", judge,
        model, reasoning, timeout, command_template,
    )
    _write_json(output / "evaluator-a.json", a)
    if not strict:
        agreement = {"mode": "single", "exact": None, "requires_adjudication": False}
        final = a
    else:
        b = _call_judge(
            packet, judge_prompt(packet, "evaluator-b"), output / "evaluator-b", judge,
            model, reasoning, timeout, command_template,
        )
        _write_json(output / "evaluator-b.json", b)
        agreement = agreement_summary(a, b)
        agreement["mode"] = "double_with_adjudication"
        if agreement["requires_adjudication"]:
            final = _call_judge(
                packet, adjudication_prompt(packet, a, b, "adjudicator-c"),
                output / "adjudicator-c", judge, model, reasoning, timeout, command_template,
            )
            _write_json(output / "adjudicator-c.json", final)
        else:
            final = a
    _write_json(output / "consensus.json", final)
    _write_json(output / "agreement.json", agreement)
    return final, agreement


def _usage_tokens(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    total = value.get("total_tokens")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return int(total)
    input_tokens = value.get("input_tokens")
    output_tokens = value.get("output_tokens")
    parts = [item for item in (input_tokens, output_tokens) if isinstance(item, (int, float)) and not isinstance(item, bool)]
    return sum(int(item) for item in parts) if parts else None

def _decorate_score(
    score: dict[str, Any], summary: dict[str, Any], judgment: dict[str, Any], agreement: dict[str, Any],
    run_name: str, condition: str,
) -> dict[str, Any]:
    score["run_name"] = run_name
    score["condition"] = condition
    score["judge"] = {
        "prompt_version": JUDGE_PROMPT_VERSION,
        "evaluator_id": judgment["evaluator_id"],
        "confidence": judgment["confidence"],
        "agreement": agreement,
    }
    score["observed"] = {
        "elapsed_seconds": float(summary.get("elapsed_seconds") or 0),
        "tokens": _usage_tokens(summary.get("agent_result", {}).get("usage")),
        "touched_files": len(summary.get("changes", {}).get("changed_paths", [])),
        "changed_paths": summary.get("changes", {}).get("changed_paths", []),
        "post_check_count": len(summary.get("criterion_results", [])),
    }
    events = [json.loads(line) for line in (Path(summary["run_dir"]) / "trajectory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    score["observed"]["tool_events"] = sum(1 for event in events if event.get("kind") in {"command_start", "command_result", "test_result", "compile_result", "tool_call", "tool_result"})
    score["trajectory_completeness"] = trajectory_completeness(summary["agent"], events)
    return score


def _condition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    success = [float(row["task_success"]) for row in rows]
    recalls = [float(row["necessary_action_recall"]) for row in rows if row["necessary_action_recall"] is not None]
    avoidable = sum(sum(1 for value in row["action_categories"].values() if value == "avoidable") for row in rows)
    missed = sum(sum(1 for value in row["action_categories"].values() if value == "missed") for row in rows)
    cost_minutes = {"observed": 0.0, "estimated": 0.0, "imputed": 0.0}
    avoidable_minutes = {"observed": 0.0, "estimated": 0.0, "imputed": 0.0}
    for row in rows:
        for action in row.get("actions", []):
            if not action.get("selected_by_agent"):
                continue
            info = row.get("action_explanations", {}).get(action["action_id"], {})
            source = info.get("cost_source", "imputed")
            minutes = float(action.get("machine_minutes", 0))
            cost_minutes[source] = cost_minutes.get(source, 0.0) + minutes
            if info.get("label") == "avoidable":
                avoidable_minutes[source] = avoidable_minutes.get(source, 0.0) + minutes
    return {
        "task_count": len(rows),
        "task_success": sum(success) / len(success) if success else 0.0,
        "necessary_action_recall": sum(recalls) / len(recalls) if recalls else None,
        "avoidable_action_count": avoidable,
        "missed_necessary_count": missed,
        "observed_elapsed_seconds": sum(row["observed"]["elapsed_seconds"] for row in rows),
        "observed_tokens": sum(row["observed"]["tokens"] or 0 for row in rows),
        "trajectory_value": sum(float(row["trajectory_value"]) for row in rows),
        "selected_action_cost": sum(float(row["selected_action_cost"]) for row in rows),
        "machine_minutes_by_source": cost_minutes,
        "avoidable_minutes_by_source": avoidable_minutes,
        "touched_files": sum(row["observed"]["touched_files"] for row in rows),
        "post_checks": sum(row["observed"]["post_check_count"] for row in rows),
        "tool_events": sum(row["observed"].get("tool_events", 0) for row in rows),
        "mean_trajectory_completeness": (sum(row["trajectory_completeness"]["score"] for row in rows) / len(rows)) if rows else 0.0,
    }

def _action_html(row: dict[str, Any], action: dict[str, Any]) -> str:
    action_id = action["action_id"]
    info = row["action_explanations"].get(action_id, {})
    label = info.get("label", row["action_categories"].get(action_id, "unresolved"))
    css = "bad" if label == "avoidable" else "warn" if label in {"missed", "unresolved"} else "good" if label == "necessary" else "blue"
    requirement = f"<p><b>Requirement:</b> {html.escape(str(info.get('requirement_id')))}</p>" if info.get("requirement_id") else ""
    consequence = f"<p><b>If omitted:</b> {html.escape(str(info.get('omission_consequence')))}</p>" if info.get("omission_consequence") else ""
    substitute = f"<p><b>Cheaper substitute:</b> {html.escape(str(info.get('cheaper_substitute')))}</p>" if info.get("cheaper_substitute") else ""
    explanation = f"<p>{html.escape(str(info.get('explanation') or 'No additional explanation.'))}</p>"
    evidence_rows = "".join(f"<li>{html.escape(str(item.get('source_id')))}: {html.escape(str(item.get('quote')))}</li>" for item in info.get("evidence", action.get("evidence", [])))
    evidence = f"<p><b>Evidence</b></p><ul>{evidence_rows}</ul>" if evidence_rows else ""
    source = str(info.get("cost_source", action.get("machine_time_source", "unknown"))).title()
    display_label = str(label).upper() + (" · HIGH COST" if label == "necessary" and float(action.get("net_action_value", 0)) < 0 else "")
    return (
        f'<div class="action"><span class="pill {css}">{html.escape(display_label)}</span>'
        f'<strong>{html.escape(str(action["description"]))}</strong>'
        f'<div class="meta">{source} machine time {float(action.get("machine_minutes",0)):.2f} min · net {float(action.get("net_action_value",0)):.2f} · confidence {float(info.get("confidence",0)):.2f}</div>'
        f'{explanation}{requirement}{consequence}{substitute}{evidence}</div>'
    )

def render_paired_report(result: dict[str, Any], output: Path) -> Path:
    baseline, intervention = result["summary"]["baseline"], result["summary"]["intervention"]
    def pct(value: Any) -> str:
        return "n/a" if value is None else f"{100 * float(value):.0f}%"
    pairs = []
    by_task: dict[str, dict[str, dict[str, Any]]] = {}
    for row in result["results"]:
        by_task.setdefault(row["task_id"], {})[row["condition"]] = row
    for task_id, conditions in by_task.items():
        columns = []
        for condition in ("baseline", "intervention"):
            row = conditions.get(condition)
            if row is None:
                columns.append(f'<div class="column"><h3>{condition.title()}</h3><p>Run unavailable.</p></div>')
                continue
            actions = "".join(_action_html(row, action) for action in row["actions"])
            agreement = row.get("judge", {}).get("agreement", {})
            agreement_text = "single judge" if agreement.get("mode") == "single" else f"judge agreement {float(agreement.get('action_label_jaccard', 0)):.0%}"
            completeness = pct(row.get("trajectory_completeness", {}).get("score"))
            columns.append(
                f'<div class="column"><h3>{condition.title()}</h3><p>Success {pct(row["task_success"])} · recall {pct(row["necessary_action_recall"])} · {html.escape(agreement_text)}</p><p class="meta">Observed {float(row["observed"]["elapsed_seconds"]):.1f}s · tokens {row["observed"]["tokens"] if row["observed"]["tokens"] is not None else "unavailable"} · touched files {row["observed"]["touched_files"]} · checks {row["observed"]["post_check_count"]} · tools {row["observed"].get("tool_events",0)} · trajectory completeness {completeness} · experimental ROI {float(row.get("trajectory_roi") or 0):.2f}</p>{actions}</div>'
            )
        pairs.append(f'<section class="panel"><h2>{html.escape(task_id)}</h2><div class="pair">{"".join(columns)}</div></section>')
    css = """
    body{margin:0;background:#f7f8fa;color:#17202a;font:15px/1.5 system-ui,sans-serif}.wrap{max-width:1200px;margin:auto;padding:36px 22px 72px}h1{font-size:38px;margin-bottom:4px}.lede,.meta{color:#667085}.cards,.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card,.panel,.column{background:white;border:1px solid #e4e7ec;border-radius:14px;padding:18px}.panel{margin-top:18px}.column{background:#fbfcfe}.action{border-top:1px solid #e4e7ec;padding:12px 0}.pill{display:inline-block;margin-right:8px;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:700}.good{background:#ecfdf3;color:#087443}.bad{background:#fef3f2;color:#b42318}.warn{background:#fff7ed;color:#b54708}.blue{background:#eff8ff;color:#175cd3}@media(max-width:760px){.cards,.pair{grid-template-columns:1fr}}
    """
    def minutes_text(row: dict[str, Any]) -> str:
        values = row["avoidable_minutes_by_source"]
        return f'{values.get("observed",0):.2f} observed + {values.get("estimated",0):.2f} estimated + {values.get("imputed",0):.2f} imputed min'
    cards = (
        f'<div class="cards"><div class="card"><b>{pct(baseline["task_success"])} → {pct(intervention["task_success"])}</b><div>Task success</div></div>'
        f'<div class="card"><b>{pct(baseline["necessary_action_recall"])} → {pct(intervention["necessary_action_recall"])}</b><div>Necessary recall</div></div>'
        f'<div class="card"><b>{baseline["avoidable_action_count"]} → {intervention["avoidable_action_count"]}</b><div>Avoidable actions</div></div>'
        f'<div class="card"><b>{baseline["missed_necessary_count"]} → {intervention["missed_necessary_count"]}</b><div>Missed necessary actions</div></div>'
        f'<div class="card"><b>{baseline["observed_elapsed_seconds"]:.1f}s → {intervention["observed_elapsed_seconds"]:.1f}s</b><div>Observed elapsed time</div></div>'
        f'<div class="card"><b>{baseline["observed_tokens"]} → {intervention["observed_tokens"]}</b><div>Observed tokens when exposed</div></div>'
        f'<div class="card"><b>{html.escape(minutes_text(baseline))}</b><div>Baseline avoidable machine time by source</div></div>'
        f'<div class="card"><b>{html.escape(minutes_text(intervention))}</b><div>Intervention avoidable machine time by source</div></div>'
        f'<div class="card"><b>{pct(baseline["mean_trajectory_completeness"])} → {pct(intervention["mean_trajectory_completeness"])}</b><div>Trajectory completeness</div></div></div>'
    )

    strict_agreements = [row.get("judge", {}).get("agreement", {}) for row in result["results"] if row.get("judge", {}).get("agreement", {}).get("mode") != "single"]
    if strict_agreements:
        extraction = sum(float(row.get("action_extraction_jaccard", 0)) for row in strict_agreements) / len(strict_agreements)
        labels = sum(float(row.get("label_agreement", 0)) for row in strict_agreements) / len(strict_agreements)
        categories = sorted({name for row in strict_agreements for name in row.get("disagreement_categories", [])})
        agreement_panel = f'<section class="panel"><h2>Judge calibration</h2><p>Action extraction agreement {extraction:.0%} · label agreement {labels:.0%}</p><p class="meta">Disagreement categories: {html.escape(", ".join(categories) if categories else "none")}</p></section>'
    else:
        agreement_panel = '<section class="panel"><h2>Judge calibration</h2><p>Single judge mode. Run with <code>--strict</code> to record extraction and label agreement.</p></section>'
    document = f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Growing Bench self-test</title><style>{css}</style></head><body><main class="wrap"><h1>Was the work worth it?</h1><p class="lede">Baseline and intervention, judged blind with the same action contract.</p>{cards}{agreement_panel}{"".join(pairs)}</main></body></html>'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    return output


def run_self_test(
    intervention: Path,
    output: Path,
    *,
    suite: str = "quick",
    task_paths: list[Path] | None = None,
    contexts: list[str] | None = None,
    agent: str = "codex",
    judge: str = "codex",
    model: str | None = None,
    judge_model: str | None = None,
    reasoning: str = "high",
    judge_reasoning: str = "high",
    timeout: float = 1200,
    command_template: str | None = None,
    judge_command_template: str | None = None,
    strict: bool = False,
    allow_partial: bool = False,
    open_report: bool = True,
    isolation: str = "copy",
) -> dict[str, Any]:
    intervention, output = intervention.resolve(), output.resolve()
    if not intervention.is_file():
        raise FileNotFoundError(f"intervention file is missing: {intervention}")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    tasks = suite_tasks(suite, task_paths)
    if contexts:
        wanted = set(contexts)
        tasks = [path for path in tasks if load_task(path)["kind"] in wanted]
        if not tasks:
            raise ValueError(f"no {suite} suite tasks match contexts {sorted(wanted)}")
    output.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    run_card = {
        "schema_version": "growing-bench-self-test-run-card-1.0",
        "suite": suite,
        "contexts": contexts or ["code", "writing", "internal_review", "external_peer_review"],
        "task_ids": [load_task(path)["task_id"] for path in tasks],
        "agent": {"adapter": agent, "model": model, "reasoning": reasoning},
        "isolation": isolation,
        "judge": {
            "adapter": judge,
            "model": judge_model,
            "reasoning": judge_reasoning,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "action_extraction_version": JUDGMENT_SCHEMA_VERSION,
            "mode": "double_with_adjudication" if strict else "single",
            "sampling": {"temperature": None, "top_p": None, "source": "adapter_default"},
            "condition_identity_blinded": True,
        },
        "intervention_file": intervention.name,
    }
    _write_json(output / "run-card.json", run_card)
    shutil.copy2(intervention, output / "intervention.md")
    for task_path in tasks:
        task = load_task(task_path)
        task_slug = task["task_id"]
        for condition in ("baseline", "intervention"):
            run_name = f"{task_slug}--{condition}"
            run_dir = output / "runs" / run_name
            summary = run_task(
                task_path, run_dir, model=model, reasoning=reasoning, timeout=timeout,
                agent=agent, intervention=intervention if condition == "intervention" else None,
                command_template=command_template, isolation=isolation,
            )
            summary["run_dir"] = str(run_dir)
            successful = summary["status"] in {"completed", "completed_pending_judgment"}
            if not successful:
                failures.append({"run": run_name, "stage": "agent", "status": summary["status"]})
                if not allow_partial:
                    continue
            if not (run_dir / "trajectory.jsonl").is_file():
                continue
            judge_dir = output / "judgments" / run_name
            try:
                judgment, agreement = _judge_one(
                    run_dir, judge_dir, judge, judge_model, judge_reasoning, timeout,
                    judge_command_template, strict,
                )
                packet = build_packet(run_dir)
                score, bundle = score_judgment(task, packet, judgment, f"self-test::{run_name}")
                _write_json(judge_dir / "bundle.json", bundle)
                score = _decorate_score(score, summary, judgment, agreement, run_name, condition)
                score["trajectory_roi"] = None if score["selected_action_cost"] <= 0 else score["trajectory_value"] / score["selected_action_cost"]
                results.append(score)
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
                failures.append({"run": run_name, "stage": "judge", "status": str(exc)})
    baseline_rows = [row for row in results if row["condition"] == "baseline"]
    intervention_rows = [row for row in results if row["condition"] == "intervention"]
    status = "completed" if not failures and len(results) == 2 * len(tasks) else "partial_failed"
    result = {
        "schema_version": "growing-bench-self-test-results-1.0",
        "status": status,
        "suite": suite,
        "strict": strict,
        "results": results,
        "failures": failures,
        "summary": {
            "baseline": _condition_summary(baseline_rows),
            "intervention": _condition_summary(intervention_rows),
        },
    }
    _write_json(output / "results.json", result)
    report = render_paired_report(result, output / "report.html")
    result["report"] = str(report)
    _write_json(output / "results.json", result)
    if open_report:
        try:
            webbrowser.open(report.as_uri())
        except OSError:
            pass
    return result
