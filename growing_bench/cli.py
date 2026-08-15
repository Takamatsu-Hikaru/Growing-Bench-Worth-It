from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .agents import BUILTIN_AGENTS
from .execution import run_task
from .health import doctor
from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_SMOKE_SOURCE, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT
from .pipeline import ingest
from .reporting import render_report
from .scoring import score_frozen_run
from .smoke import run_smoke


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _product_smoke(output: Path, source: Path) -> dict[str, object]:
    result = run_smoke(output, source)
    adapter_output = output.resolve() / "live-adapter"
    command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
    live = run_task(
        REPOSITORY_ROOT / "examples" / "tasks" / "adapter-smoke.json",
        adapter_output,
        agent="command",
        command_template=command,
    )
    live_report = render_report(adapter_output)
    result["live_adapter"] = {
        "status": live["status"],
        "trajectory": str(adapter_output / "trajectory.jsonl"),
        "report": str(live_report),
        "uses_external_model": False,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="growing-bench")
    parser.add_argument("--version", action="version", version=f"growing-bench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check agents and local fixture runtimes")
    smoke = sub.add_parser("smoke", help="run the offline score and real-workspace adapter demo")
    smoke.add_argument("--output", type=Path, default=Path("runs/smoke"))
    smoke.add_argument("--source", type=Path, default=DEFAULT_SMOKE_SOURCE)
    run = sub.add_parser("run", help="run one materialized task with any supported agent")
    run.add_argument("task", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex")
    run.add_argument("--model")
    run.add_argument("--reasoning", default="high")
    run.add_argument("--timeout-seconds", type=float, default=1200)
    run.add_argument("--intervention", type=Path)
    run.add_argument("--command-template", help="JSON command array for --agent command")
    add = sub.add_parser("ingest", help="preflight and append a Markdown case")
    add.add_argument("case", type=Path)
    add.add_argument("--track")
    add.add_argument("--tracks-root", type=Path, default=DEFAULT_TRACKS_ROOT)
    add.add_argument("--catalog", type=Path, default=DEFAULT_FIXTURE_CATALOG)
    add.add_argument("--materialize", action="store_true")
    add.add_argument("--validate", action="store_true")
    judge = sub.add_parser("judge", help="recompute scores from frozen evaluator ledgers")
    judge.add_argument("run_dir", type=Path)
    report = sub.add_parser("report", help="render a scored run or live run as HTML")
    report.add_argument("run_dir", type=Path)
    report.add_argument("--output", type=Path)
    export = sub.add_parser("export-hf", help="prepare a Hugging Face Dataset repository")
    export.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        _print(doctor())
    elif args.command == "smoke":
        _print(_product_smoke(args.output, args.source))
    elif args.command == "run":
        _print(run_task(args.task, args.output, args.model, args.reasoning, args.timeout_seconds, args.agent, args.intervention, args.command_template))
    elif args.command == "ingest":
        _print(ingest(args.case, args.tracks_root, args.catalog, args.track, args.materialize or args.validate, args.validate))
    elif args.command == "judge":
        _print({"status": "completed", "results": score_frozen_run(args.run_dir)})
    elif args.command == "report":
        _print({"status": "completed", "report": str(render_report(args.run_dir.resolve(), args.output))})
    else:
        return subprocess.run([sys.executable, str(REPOSITORY_ROOT / "tools" / "export_huggingface.py"), "--output", str(args.output)], cwd=REPOSITORY_ROOT, check=False).returncode
    return 0

