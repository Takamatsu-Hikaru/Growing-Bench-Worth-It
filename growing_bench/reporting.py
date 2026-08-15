from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


STYLE = """
:root{--ink:#17202a;--muted:#667085;--line:#e4e7ec;--good:#087443;--bad:#b42318;--warn:#b54708;--blue:#175cd3;--paper:#fff;--wash:#f8fafc}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:44px 24px 80px}h1{font-size:38px;letter-spacing:-.04em;margin:0 0 8px}.lede{font-size:19px;color:var(--muted);margin:0 0 30px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:24px 0}.card,.panel{background:var(--paper);border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px #1018280d}.card{padding:18px}.card b{display:block;font-size:28px}.card span{color:var(--muted)}.panel{padding:22px;margin:18px 0}.task{border-left:5px solid var(--blue)}.action{padding:14px 0;border-top:1px solid var(--line)}.action:first-child{border-top:0}.action-head{display:flex;gap:12px;align-items:flex-start}.pill{display:inline-block;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700;white-space:nowrap}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.pill.good{background:#ecfdf3}.pill.bad{background:#fef3f2}.pill.warn{background:#fffaeb}.pill.missed{background:#eff8ff;color:var(--blue)}.metrics{color:var(--muted);font-size:13px;margin-top:5px}details{margin-top:8px}summary{cursor:pointer;color:var(--blue)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101828;color:#f2f4f7;border-radius:10px;padding:15px;max-height:420px;overflow:auto}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.secondary{color:var(--muted);font-size:13px}.bar{height:7px;background:#eaecf0;border-radius:999px;overflow:hidden;margin-top:8px}.bar>i{display:block;height:100%;background:var(--blue)}@media(max-width:650px){h1{font-size:30px}.wrap{padding:28px 14px}.action-head{display:block}.pill{margin-bottom:7px}}
"""


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _page(title: str, body: str) -> str:
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main class="wrap">{body}</main></body></html>'


def _pct(value: Any) -> str:
    return "—" if value is None else f"{100 * float(value):.0f}%"


def _card(value: str, label: str, cls: str = "") -> str:
    return f'<div class="card"><b class="{cls}">{html.escape(value)}</b><span>{html.escape(label)}</span></div>'


def _bundle_map(run_dir: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for path in (run_dir / "bundles").glob("*.json") if (run_dir / "bundles").is_dir() else []:
        value = json.loads(path.read_text(encoding="utf-8"))
        result[str(value.get("trajectory", {}).get("trajectory_id"))] = value
    return result


def _action_html(action: dict[str, Any], bundle: dict[str, Any]) -> str:
    action_id = action.get("action_id")
    bundled = next((x for x in bundle.get("actions", []) if x.get("action_id") == action_id), {})
    annotation = next((x for x in bundle.get("annotations", []) if x.get("action_id") == action_id), {})
    selected, status, net = action.get("selected_by_agent"), action.get("status"), float(action.get("net_action_value", 0))
    if status == "missed": label, cls = "MISSED", "missed"
    elif selected and net < 0: label, cls = "LOW VALUE", "bad"
    elif selected: label, cls = "VALUE", "good"
    else: label, cls = "NOT SELECTED", "warn"
    evidence = bundled.get("evidence", [])
    evidence_html = "".join(f'<li>“{html.escape(str(e.get("quote", ""))) }”</li>' for e in evidence)
    substitute = annotation.get("cheaper_substitute")
    substitute_html = "" if not substitute else f'<p><strong>Cheaper substitute:</strong> {html.escape(str(substitute.get("description", "")))}</p>'
    details = f'<details><summary>Evidence and alternative</summary>{substitute_html}<ul>{evidence_html or "<li>No public evidence excerpt.</li>"}</ul></details>'
    return f'<div class="action"><div class="action-head"><span class="pill {cls}">{label}</span><div><strong>{html.escape(str(action.get("description", "")))}</strong><div class="metrics">{html.escape(str(bundled.get("action_type", "action")))} · {float(action.get("human_minutes", 0)):.1f} human min · cost {float(action.get("normalized_cost", 0)):.2f} · net value {net:.2f}</div></div></div>{details}</div>'


def _scored_report(run_dir: Path) -> str:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    scores = _read_rows(run_dir / "scores.jsonl")
    bundles = _bundle_map(run_dir)
    success = float(results.get("mean_task_success", 0)); recall = float(results.get("mean_necessary_action_recall", 0)); avoidable = float(results.get("total_avoidable_human_minutes", 0)); unnecessary = sum(int(x.get("unnecessary_action_count", 0)) for x in scores); missed = sum(int(x.get("reference_required_action_count", 0)) * float(x.get("missed_required_action_rate") or 0) for x in scores)
    cards = "".join([_card(_pct(success), "Mean task success", "good" if success >= .8 else "warn"), _card(_pct(recall), "Necessary-action recall", "good" if recall >= .8 else "warn"), _card(f"{avoidable:.0f} min", "Avoidable human time", "bad" if avoidable else "good"), _card(str(unnecessary), "Unnecessary actions", "bad" if unnecessary else "good"), _card(f"{missed:.0f}", "Required actions missed", "warn" if missed else "good")])
    task_html = []
    for score in scores:
        bundle = bundles.get(str(score.get("trajectory_id")), {})
        action_html = "".join(_action_html(action, bundle) for action in score.get("actions", []))
        summary = f"Task success {_pct(score.get('task_success'))}; recalled {_pct(score.get('necessary_action_recall'))} of necessary actions; {float(score.get('avoidable_human_minutes', 0)):.0f} avoidable human minutes."
        task_html.append(f'<section class="panel task"><h2>{html.escape(str(score.get("task_id")))}</h2><p>{html.escape(summary)}</p><div class="bar"><i style="width:{100*float(score.get("task_success",0)):.1f}%"></i></div><p class="secondary">Condition: {html.escape(str(score.get("intervention_id")))} · ROI {float(score.get("trajectory_roi") or 0):.2f} (secondary diagnostic)</p><h3>Action timeline</h3>{action_html}</section>')
    comparison_rows = "".join(f'<tr><td>{html.escape(str(s.get("task_id")))}</td><td>{html.escape(str(s.get("intervention_id")))}</td><td>{_pct(s.get("task_success"))}</td><td>{_pct(s.get("necessary_action_recall"))}</td><td>{float(s.get("avoidable_human_minutes",0)):.0f} min</td><td>{int(s.get("unnecessary_action_count",0))}</td></tr>' for s in scores)
    body = f'<h1>Was the work worth it?</h1><p class="lede">Correctness, missed value, and avoidable cost—shown separately.</p><section class="cards">{cards}</section><section class="panel"><h2>Baseline / intervention view</h2><table><thead><tr><th>Task</th><th>Condition</th><th>Success</th><th>Recall</th><th>Avoidable time</th><th>Unnecessary</th></tr></thead><tbody>{comparison_rows}</tbody></table><p class="secondary">ROI is retained as a derived diagnostic: portfolio ROI {float(results.get("portfolio_roi") or 0):.2f}. It is not a leaderboard score.</p></section>{"".join(task_html)}<p class="secondary">AI-consensus silver labels; this report does not claim human gold or real-user satisfaction.</p>'
    return _page("Growing Bench report", body)


def _live_report(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")); task = json.loads((run_dir / "task.json").read_text(encoding="utf-8")); final = (run_dir / "agent" / "final.md").read_text(encoding="utf-8") if (run_dir / "agent" / "final.md").is_file() else ""; diff = (run_dir / "changes.diff").read_text(encoding="utf-8") if (run_dir / "changes.diff").is_file() else ""; checks = json.loads((run_dir / "checks.after.json").read_text(encoding="utf-8")) if (run_dir / "checks.after.json").is_file() else []
    elapsed = float(summary.get("agent_result", {}).get("elapsed_seconds", 0)); changed = len(summary.get("changes", {}).get("changed_paths", [])); unexpected = len(summary.get("unexpected_changed_paths", [])); completed = summary.get("status") == "completed"
    cards = "".join([_card("PASS" if completed else "FAIL", "Task execution", "good" if completed else "bad"), _card(f"{elapsed:.1f}s", "Agent time"), _card(str(changed), "Changed paths"), _card(str(unexpected), "Out-of-scope paths", "bad" if unexpected else "good")])
    check_rows = "".join(f'<tr><td>{html.escape(str(c.get("name")))}</td><td class="{"good" if c.get("passed") else "bad"}">{"pass" if c.get("passed") else "fail"}</td><td>{float(c.get("elapsed_seconds",0)):.2f}s</td></tr>' for c in checks)
    body = f'<h1>Real workspace run</h1><p class="lede">{html.escape(str(task.get("task_id")))} · {html.escape(str(summary.get("agent")))}</p><section class="cards">{cards}</section><section class="panel"><h2>Completion checks</h2><table><thead><tr><th>Check</th><th>Status</th><th>Time</th></tr></thead><tbody>{check_rows}</tbody></table></section><section class="panel"><h2>Prompt</h2><pre>{html.escape(str(task.get("prompt", "")))}</pre></section><section class="panel"><h2>Final response</h2><pre>{html.escape(final)}</pre></section><section class="panel"><h2>Workspace diff</h2><pre>{html.escape(diff or "(no text diff)")}</pre></section>'
    return _page("Growing Bench live run", body)


def render_report(run_dir: Path, output: Path | None = None) -> Path:
    run_dir = run_dir.resolve()
    if (run_dir / "results.json").is_file() and (run_dir / "scores.jsonl").is_file(): document = _scored_report(run_dir)
    elif (run_dir / "summary.json").is_file() and (run_dir / "task.json").is_file(): document = _live_report(run_dir)
    else: raise FileNotFoundError("expected a scored run or a live run directory")
    target = output.resolve() if output else run_dir / "report.html"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(document, encoding="utf-8", newline="\n"); return target

