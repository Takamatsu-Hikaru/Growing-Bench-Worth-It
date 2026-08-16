from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any


STYLE = """
:root{--ink:#17202a;--muted:#667085;--line:#e4e7ec;--good:#087443;--bad:#b42318;--warn:#b54708;--blue:#175cd3;--paper:#fff;--wash:#f8fafc}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}.wrap{max-width:1120px;margin:auto;padding:42px 22px 80px}h1{font-size:38px;letter-spacing:-.04em;margin:0 0 8px}.lede{font-size:19px;color:var(--muted);margin:0 0 28px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:13px;margin:22px 0}.card,.panel{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px #1018280d}.card{padding:17px}.card b{display:block;font-size:27px}.card span,.muted{color:var(--muted)}.panel{padding:21px;margin:17px 0}.task{border-left:5px solid var(--blue)}.action{padding:13px 0;border-top:1px solid var(--line)}.action:first-child{border-top:0}.head{display:flex;gap:11px;align-items:flex-start}.pill{display:inline-block;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700;white-space:nowrap}.necessary_efficient{background:#ecfdf3;color:var(--good)}.necessary_expensive{background:#fff4e5;color:var(--warn)}.avoidable,.failed_reverted{background:#fef3f2;color:var(--bad)}.optional_conditional,.proposed_not_executed{background:#eff8ff;color:var(--blue)}.unresolved,.missed{background:#f2f4f7;color:#344054}.metrics{color:var(--muted);font-size:13px;margin-top:4px}details{margin-top:7px}summary{cursor:pointer;color:var(--blue)}code{font-size:12px}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:12px;text-transform:uppercase}.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}@media(max-width:650px){h1{font-size:30px}.wrap{padding:26px 13px}.head{display:block}.pill{margin-bottom:7px}}
"""


LABELS = {
    "necessary_efficient": "NECESSARY · EFFICIENT",
    "necessary_expensive": "NECESSARY · EXPENSIVE",
    "avoidable": "AVOIDABLE",
    "optional_conditional": "OPTIONAL / CONDITIONAL",
    "proposed_not_executed": "PROPOSED, NOT EXECUTED",
    "failed_reverted": "FAILED / REVERTED",
    "unresolved": "UNRESOLVED",
    "missed": "MISSED",
}


def _card(value: str, label: str, cls: str = "") -> str:
    return f'<div class="card"><b class="{cls}">{html.escape(value)}</b><span>{html.escape(label)}</span></div>'


def _percent(value: float) -> str:
    return f"{100 * value:.0f}%"


def _action(row: dict[str, Any], category: str) -> str:
    label = LABELS.get(category, category.upper().replace("_", " "))
    cost = float(row.get("normalized_cost", 0))
    machine = float(row.get("machine_minutes", 0))
    return (
        f'<div class="action"><div class="head"><span class="pill {html.escape(category)}">{html.escape(label)}</span>'
        f'<div><strong>{html.escape(str(row.get("description", "")))}</strong>'
        f'<div class="metrics">status {html.escape(str(row.get("status")))} · machine {machine:.2f} min · normalized cost {cost:.3f} · net value {float(row.get("net_action_value",0)):.3f}</div>'
        f'</div></div></div>'
    )


def render_workspace_report(run_dir: Path, output: Path | None = None) -> Path:
    run_dir = run_dir.resolve()
    payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = payload["results"]
    success = sum(float(r["task_success"]) for r in rows) / len(rows)
    recall = sum(float(r["necessary_action_recall"]) for r in rows) / len(rows)
    category_counts: Counter[str] = Counter()
    avoidable_machine = 0.0
    task_sections: list[str] = []
    for row in rows:
        categories = row.get("action_categories", {})
        category_counts.update(categories.values())
        action_html = []
        for action in row.get("actions", []):
            category = categories.get(action["action_id"], "unresolved")
            if category in {"avoidable", "failed_reverted"} and action.get("selected_by_agent"):
                avoidable_machine += float(action.get("machine_minutes", 0))
            action_html.append(_action(action, category))
        title = row.get("run_name") or row["task_id"]
        summary = (
            f"Success {_percent(float(row['task_success']))}; necessary-action recall "
            f"{_percent(float(row['necessary_action_recall']))}; trajectory value {float(row['trajectory_value']):.2f}."
        )
        task_sections.append(
            f'<section class="panel task"><h2>{html.escape(str(title))}</h2><p>{html.escape(summary)}</p>'
            f'<p class="muted"><code>{html.escape(str(row["task_id"]))}</code> · elapsed {float(row.get("trajectory_elapsed_seconds",0)):.1f}s</p>'
            f'<h3>Action timeline</h3>{"".join(action_html)}</section>'
        )
    selected_avoidable = category_counts["avoidable"] + category_counts["failed_reverted"]
    cards = "".join([
        _card(_percent(success), "Task success", "good" if success == 1 else "warn"),
        _card(_percent(recall), "Necessary-action recall", "good" if recall >= .8 else "warn"),
        _card(str(selected_avoidable), "Avoidable / failed actions", "bad" if selected_avoidable else "good"),
        _card(f"{avoidable_machine:.2f} min", "Observed/estimated avoidable machine time", "bad" if avoidable_machine else "good"),
    ])
    category_rows = "".join(
        f'<tr><td>{html.escape(LABELS.get(name, name))}</td><td>{count}</td></tr>'
        for name, count in sorted(category_counts.items())
    )
    body = (
        '<h1>Was the work worth it?</h1>'
        '<p class="lede">Correctness, necessary work, missed value, and avoidable cost—kept separate.</p>'
        f'<section class="cards">{cards}</section>'
        f'<section class="panel"><h2>Eight-task calibration slice</h2><table><thead><tr><th>Action category</th><th>Count</th></tr></thead><tbody>{category_rows}</tbody></table>'
        '<p class="muted">AI-consensus silver labels. This is an evaluation-pipeline calibration, not the 50-task model leaderboard and not real-user satisfaction.</p></section>'
        + "".join(task_sections)
    )
    document = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Growing Bench workspace report</title><style>{STYLE}</style></head><body><main class="wrap">{body}</main></body></html>'
    target = output.resolve() if output else run_dir / "report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")
    return target
