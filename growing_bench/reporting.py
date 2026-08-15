from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


STYLE = "body{font:16px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#17202a}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d5d8dc;padding:8px;text-align:left}th{background:#f4f6f7}code,pre{background:#f4f6f7;padding:4px;white-space:pre-wrap}.ok{color:#177245}.bad{color:#b03a2e}"


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _page(title: str, body: str) -> str:
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>'


def _scored_report(run_dir: Path) -> str:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = []
    for score in _read_rows(run_dir / "scores.jsonl"):
        rows.append("<tr>" + "".join([
            f"<td>{html.escape(str(score.get('task_id', '')))}</td>",
            f"<td>{html.escape(str(score.get('intervention_id', '')))}</td>",
            f"<td>{float(score.get('task_success', 0)):.3f}</td>",
            f"<td>{float(score.get('unnecessary_action_rate', 0)):.3f}</td>",
            f"<td>{float(score.get('trajectory_value', 0)):.3f}</td>",
        ]) + "</tr>")
    metrics = "".join(f"<li><strong>{html.escape(str(k))}</strong>: {html.escape(str(v))}</li>" for k, v in results.items() if k not in {"schema_version", "roi_aggregation"})
    return _page("Growing Bench score report", f"<h1>Growing Bench score report</h1><p>AI-consensus silver annotations; not a human-satisfaction claim or leaderboard.</p><h2>Summary</h2><ul>{metrics}</ul><p><code>{html.escape(str(results.get('roi_aggregation', '')))}</code></p><h2>Trajectories</h2><table><thead><tr><th>Task</th><th>Condition</th><th>Success</th><th>Unnecessary rate</th><th>Value</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")


def _live_report(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    task = json.loads((run_dir / "task.json").read_text(encoding="utf-8"))
    final = (run_dir / "agent" / "final.md").read_text(encoding="utf-8") if (run_dir / "agent" / "final.md").is_file() else ""
    diff = (run_dir / "changes.diff").read_text(encoding="utf-8") if (run_dir / "changes.diff").is_file() else ""
    checks = json.loads((run_dir / "checks.after.json").read_text(encoding="utf-8")) if (run_dir / "checks.after.json").is_file() else []
    check_rows = "".join(f"<tr><td>{html.escape(str(c.get('name')))}</td><td class={'ok' if c.get('passed') else 'bad'}>{'pass' if c.get('passed') else 'fail'}</td><td>{float(c.get('elapsed_seconds', 0)):.2f}s</td></tr>" for c in checks)
    status_class = "ok" if summary.get("status") == "completed" else "bad"
    body = f"<h1>Growing Bench live run</h1><p><strong>Task:</strong> {html.escape(str(task.get('task_id')))} · <strong>Agent:</strong> {html.escape(str(summary.get('agent')))} · <strong class={status_class}>{html.escape(str(summary.get('status')))}</strong></p><h2>Prompt</h2><pre>{html.escape(str(task.get('prompt', '')))}</pre><h2>Checks</h2><table><thead><tr><th>Check</th><th>Status</th><th>Time</th></tr></thead><tbody>{check_rows}</tbody></table><h2>Final response</h2><pre>{html.escape(final)}</pre><h2>Workspace diff</h2><pre>{html.escape(diff or '(no text diff)')}</pre>"
    return _page("Growing Bench live run", body)


def render_report(run_dir: Path, output: Path | None = None) -> Path:
    run_dir = run_dir.resolve()
    if (run_dir / "results.json").is_file() and (run_dir / "scores.jsonl").is_file():
        document = _scored_report(run_dir)
    elif (run_dir / "summary.json").is_file() and (run_dir / "task.json").is_file():
        document = _live_report(run_dir)
    else:
        raise FileNotFoundError("expected a scored run or a live run directory")
    target = output.resolve() if output else (run_dir / "report.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")
    return target
