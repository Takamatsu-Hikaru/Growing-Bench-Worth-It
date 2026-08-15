from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .agents import BUILTIN_AGENTS
from .execution import run_task
from .health import doctor
from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_SMOKE_SOURCE, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT
from .pipeline import ingest, preflight
from .reporting import render_report
from .scoring import score_frozen_run
from .smoke import run_smoke


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _human(command: str, value: dict[str, Any]) -> None:
    if command == "doctor":
        print("Agent          Available  Version")
        print("-------------  ---------  -------")
        for name, row in value["agents"].items():
            print(f"{name:<13}  {'yes' if row['available'] else 'no':<9}  {row.get('version') or '-'}")
        print(f"\nOffline smoke: ready · live agents found: {value['live_agent_count']}")
    elif command == "smoke":
        live = value["live_adapter"]
        print("✓ Recomputed four scored trajectories without model calls")
        print(f"✓ Real workspace adapter: {live['status']}")
        print(f"✓ Score report: {value['report']}")
        print(f"✓ Workspace report: {live['report']}")
    elif command == "run":
        mark = "✓" if value.get("status") == "completed" else "!"
        print(f"{mark} Run {value.get('status')}: {value.get('task_id')}")
        print(f"  post-checks: {'pass' if value.get('post_checks_passed') else 'fail'}")
        print(f"  allowed scope: {'pass' if value.get('allowed_paths_ok') else 'fail'}")
        print(f"  trajectory: {value.get('artifacts', {}).get('trajectory', '-')}")
    elif command == "check":
        mark = "✓" if value["status"] == "ready_for_materialization" else "!"
        print(f"{mark} {value['case_id']}: {value['status']}")
        for name, passed in value["checks"].items():
            print(f"  {'✓' if passed else '!'} {name}")
        if value["missing"]:
            print("  Missing: " + ", ".join(value["missing"]))
        print("\nNext: growing-bench ingest <case.md> --materialize --validate")
    elif command == "ingest":
        print(f"✓ Case staged: {value['ingest']['candidate']}")
        if "materialize" in value:
            print(f"✓ Task materialized: {value['materialize']['task']}")
        if "validate" in value:
            print(f"{'✓' if value['validate']['status'] == 'validated' else '!'} Baseline: {value['validate']['status']}")
        print("! Reference actions remain silver_pending until AI consensus judging")
    elif command == "init-case":
        print(f"✓ Case template created: {value['path']}")
        print(f"Next: growing-bench ingest {value['path']} --check")
    elif command == "report":
        print(f"✓ Report: {value['report']}")
    elif command == "judge":
        print(f"✓ Recomputed {value['results']['trajectory_count']} scored trajectories")
        print(f"  results: {value['results_path']}")
    else:
        _json(value)


def _emit(command: str, value: dict[str, Any], as_json: bool) -> None:
    _json(value) if as_json else _human(command, value)


def _product_smoke(output: Path, source: Path) -> dict[str, Any]:
    result = run_smoke(output, source)
    adapter_output = output.resolve() / "live-adapter"
    command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
    live = run_task(REPOSITORY_ROOT / "examples" / "tasks" / "adapter-smoke.json", adapter_output, agent="command", command_template=command)
    live_report = render_report(adapter_output)
    result["live_adapter"] = {"status": live["status"], "trajectory": str(adapter_output / "trajectory.jsonl"), "report": str(live_report), "uses_external_model": False}
    return result


def _init_case(name: str, output: Path | None) -> dict[str, Any]:
    if not SLUG.fullmatch(name):
        raise ValueError("case name must be a lowercase slug")
    target = (output or Path(f"{name}.md")).resolve()
    if target.exists():
        raise FileExistsError(f"case file already exists: {target}")
    template = f'''---
{{
  "case_id": "{name}",
  "track_id": "track-YYYY-MM-topic",
  "title": "Describe the frustrating agent behavior",
  "domain": "code",
  "review_context": "not_applicable",
  "environment_family": "repo_markdown_renderer_reviewed",
  "source": "project-authored case",
  "permission_to_publish": false,
  "pair_id": "add-a-pair-id",
  "variant": "describe-this-variant",
  "allowed_paths": []
}}
---

## Task

Replace this with the exact task shown to the agent.

## Completion criteria

- Replace this with an observable outcome.
- Add the smallest second criterion needed to distinguish success from plausible-looking output.

## Observed bad response

Paste a redacted visible response or describe the concrete behavior.

## Why this is a problem

Explain the wasted work, missed value, scope expansion, or interaction burden.
'''
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template, encoding="utf-8", newline="\n")
    return {"status": "created", "path": str(target)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="growing-bench")
    parser.add_argument("--version", action="version", version=f"growing-bench {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check agents and local fixture runtimes")
    smoke = sub.add_parser("smoke", help="run the offline score and real-workspace adapter demo")
    smoke.add_argument("--output", type=Path, default=Path("runs/smoke")); smoke.add_argument("--source", type=Path, default=DEFAULT_SMOKE_SOURCE)
    run = sub.add_parser("run", help="run one materialized task with any supported agent")
    run.add_argument("task", type=Path); run.add_argument("--output", type=Path, required=True); run.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex"); run.add_argument("--model"); run.add_argument("--reasoning", default="high"); run.add_argument("--timeout-seconds", type=float, default=1200); run.add_argument("--intervention", type=Path); run.add_argument("--command-template", help="JSON command array for --agent command")
    init = sub.add_parser("init-case", help="create a contribution-ready Markdown case template")
    init.add_argument("name"); init.add_argument("--output", type=Path)
    add = sub.add_parser("ingest", help="check or append a Markdown case")
    add.add_argument("case", type=Path); add.add_argument("--track"); add.add_argument("--tracks-root", type=Path, default=DEFAULT_TRACKS_ROOT); add.add_argument("--catalog", type=Path, default=DEFAULT_FIXTURE_CATALOG); add.add_argument("--check", action="store_true", help="preflight only; write nothing"); add.add_argument("--materialize", action="store_true"); add.add_argument("--validate", action="store_true")
    judge = sub.add_parser("judge", help="recompute scores from frozen evaluator ledgers"); judge.add_argument("run_dir", type=Path)
    report = sub.add_parser("report", help="render a scored run or live run as HTML"); report.add_argument("run_dir", type=Path); report.add_argument("--output", type=Path)
    export = sub.add_parser("export-hf", help="prepare a Hugging Face Dataset repository"); export.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    return parser


def main() -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "doctor": value = doctor()
        elif args.command == "smoke": value = _product_smoke(args.output, args.source)
        elif args.command == "run": value = run_task(args.task, args.output, args.model, args.reasoning, args.timeout_seconds, args.agent, args.intervention, args.command_template)
        elif args.command == "init-case": value = _init_case(args.name, args.output)
        elif args.command == "ingest":
            if args.check and (args.materialize or args.validate):
                parser.error("--check cannot be combined with --materialize or --validate")
            if args.check:
                value = preflight(args.case.resolve(), args.tracks_root.resolve(), args.catalog.resolve(), args.track)
                _emit("check", value, args.json); return 0 if value["status"] == "ready_for_materialization" else 2
            value = ingest(args.case, args.tracks_root, args.catalog, args.track, args.materialize or args.validate, args.validate)
        elif args.command == "judge":
            results = score_frozen_run(args.run_dir); value = {"status": "completed", "results": results, "results_path": str(args.run_dir.resolve() / "results.json")}
        elif args.command == "report": value = {"status": "completed", "report": str(render_report(args.run_dir.resolve(), args.output))}
        else:
            return subprocess.run([sys.executable, str(REPOSITORY_ROOT / "tools" / "export_huggingface.py"), "--output", str(args.output)], cwd=REPOSITORY_ROOT, check=False).returncode
        _emit(args.command, value, args.json)
        return 0
    except (FileNotFoundError, FileExistsError, ValueError, TimeoutError) as exc:
        if args.json: _json({"status": "error", "error": str(exc)})
        else: print(f"Error: {exc}", file=sys.stderr)
        return 2

