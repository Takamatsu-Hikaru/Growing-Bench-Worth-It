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
from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_SMOKE_SOURCE, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT, SOURCE_ROOT
from .pipeline import ingest as ingest_legacy, preflight as preflight_legacy
from .reporting import render_report
from .scoring import score_frozen_run
from .smoke import run_smoke
from .workspace_ingest import materialize_workspace_case, preflight_workspace_case
from .workspace_reporting import render_workspace_report


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        method = getattr(stream, "reconfigure", None)
        if callable(method):
            method(encoding="utf-8", errors="backslashreplace")


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _human(command: str, value: dict[str, Any]) -> None:
    if command == "doctor":
        print("Agent          Available  Version")
        print("-------------  ---------  -------")
        for name, row in value["agents"].items():
            print(f"{name:<13}  {'yes' if row['available'] else 'no':<9}  {row.get('version') or '-'}")
        print(f"\nOffline smoke: ready; live agents found: {value['live_agent_count']}")
    elif command == "smoke":
        print("OK Recomputed four scored trajectories without model calls")
        print(f"OK Real workspace adapter: {value['live_adapter']['status']}")
        print(f"OK Score report: {value['report']}")
        print(f"OK Workspace report: {value['live_adapter']['report']}")
    elif command == "run":
        ok = value.get("post_checks_passed") and value.get("allowed_paths_ok")
        print(f"{'OK' if ok else 'WARN'} Run {value.get('status')}: {value.get('task_id')}")
        print(f"  completion checks: {'pass' if value.get('post_checks_passed') else 'fail'}")
        print(f"  allowed scope: {'pass' if value.get('allowed_paths_ok') else 'fail'}")
        print(f"  trajectory: {value.get('artifacts', {}).get('trajectory', '-')}")
    elif command in {"check", "ingest"}:
        status = value.get("status") or value.get("candidate", {}).get("status") or value.get("ingest", {}).get("status")
        ok = status in {"ready_for_ai_curation", "ready_for_materialization", "validated"}
        print(f"{'OK' if ok else 'WARN'} {status}")
        if value.get("missing"):
            print("  Missing: " + ", ".join(value["missing"]))
        if value.get("task"):
            print(f"  Task: {value['task']}")
    elif command == "init-case":
        print(f"OK Portable case created: {value['path']}")
        print("  Add fixture/ and reference/, then run ingest --check.")
    elif command == "report":
        print(f"OK Report: {value['report']}")
    elif command == "judge":
        print(f"OK Recomputed {value['results']['trajectory_count']} scored trajectories")
    else:
        _json(value)


def _emit(command: str, value: dict[str, Any], as_json: bool) -> None:
    _json(value) if as_json else _human(command, value)


def _product_smoke(output: Path, source: Path) -> dict[str, Any]:
    result = run_smoke(output, source)
    adapter_output = output.resolve() / "live-adapter"
    command = json.dumps([sys.executable, "-m", "growing_bench.demo_agent", "{workspace}"])
    task = REPOSITORY_ROOT / "examples" / "tasks" / "adapter-smoke.json"
    live = run_task(task, adapter_output, agent="command", command_template=command)
    result["live_adapter"] = {"status": live["status"], "trajectory": str(adapter_output / "trajectory.jsonl"), "report": str(render_report(adapter_output)), "uses_external_model": False}
    return result


def _init_case(name: str, output: Path | None) -> dict[str, Any]:
    if not SLUG.fullmatch(name):
        raise ValueError("case name must be a lowercase slug")
    requested = (output or Path(name)).resolve()
    if output is not None and requested.suffix.casefold() == ".md":
        case, directory = requested, requested.parent
        if case.exists():
            raise FileExistsError(f"case file already exists: {case}")
    else:
        directory, case = requested, requested / "case.md"
        if directory.exists():
            raise FileExistsError(f"case directory already exists: {directory}")
    (directory / "fixture").mkdir(parents=True, exist_ok=True)
    (directory / "reference").mkdir(exist_ok=True)
    template = f'''---
{{
  "case_id": "{name}",
  "track_id": "workspace-community-YYYY-MM",
  "title": "Describe the concrete agent failure",
  "domain": "code",
  "review_context": "not_applicable",
  "environment_family": "portable_workspace_package",
  "source": "project-authored case",
  "permission_to_publish": false,
  "variant": "standalone",
  "fixture_source": "fixture",
  "reference_source": "reference",
  "allowed_paths": ["replace-me"],
  "checks": [{{"name": "focused-check", "command": ["python", "-m", "checks.check"]}}],
  "baseline_expectation": "failing",
  "expected_failure": {{"check": "focused-check", "returncode": 1, "contains": "replace-me"}}
}}
---

## Task

Replace with the exact task shown to the agent.

## Completion criteria

- Add an observable executable outcome.
- Add the smallest semantic criterion needed to reject plausible-looking bad work.

## Observed bad response

Paste a redacted response or describe the concrete trajectory failure.

## Why this is a problem

Explain wasted work, missed value, scope expansion, or interaction burden.
'''
    case.write_text(template, encoding="utf-8", newline="\n")
    return {"status": "created", "path": str(case), "fixture": str(directory / "fixture"), "reference": str(directory / "reference")}


def _portable(case: Path) -> bool:
    return "portable_workspace_package" in case.read_text(encoding="utf-8")[:5000]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="growing-bench")
    parser.add_argument("--version", action="version", version=f"growing-bench {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check local agents and runtime resources")
    smoke = sub.add_parser("smoke", help="run the offline score and real-workspace demo"); smoke.add_argument("--output", type=Path, default=Path("runs/smoke")); smoke.add_argument("--source", type=Path, default=DEFAULT_SMOKE_SOURCE)
    run = sub.add_parser("run", help="run one materialized workspace task"); run.add_argument("task", type=Path); run.add_argument("--output", type=Path, required=True); run.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex"); run.add_argument("--model"); run.add_argument("--reasoning", default="high"); run.add_argument("--timeout-seconds", type=float, default=1200); run.add_argument("--intervention", type=Path); run.add_argument("--command-template")
    init = sub.add_parser("init-case", help="create a portable Markdown + workspace case"); init.add_argument("name"); init.add_argument("--output", type=Path)
    add = sub.add_parser("ingest", help="preflight or materialize a Markdown case"); add.add_argument("case", type=Path); add.add_argument("--track"); add.add_argument("--tracks-root", type=Path, default=DEFAULT_TRACKS_ROOT); add.add_argument("--catalog", type=Path, default=DEFAULT_FIXTURE_CATALOG); add.add_argument("--check", action="store_true"); add.add_argument("--materialize", action="store_true"); add.add_argument("--validate", action="store_true"); add.add_argument("--curation", type=Path, help="AI curator JSON required for portable workspace materialization")
    judge = sub.add_parser("judge", help="recompute scores from frozen evaluator ledgers"); judge.add_argument("run_dir", type=Path)
    report = sub.add_parser("report", help="render a scored or live run as HTML"); report.add_argument("run_dir", type=Path); report.add_argument("--output", type=Path)
    export = sub.add_parser("export-hf", help="prepare a Hugging Face Dataset repository"); export.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    return parser


def main() -> int:
    _configure_output(); parser = build_parser(); args = parser.parse_args()
    try:
        if args.command == "doctor": value = doctor()
        elif args.command == "smoke": value = _product_smoke(args.output, args.source)
        elif args.command == "run": value = run_task(args.task, args.output, args.model, args.reasoning, args.timeout_seconds, args.agent, args.intervention, args.command_template)
        elif args.command == "init-case": value = _init_case(args.name, args.output)
        elif args.command == "ingest":
            case = args.case.resolve()
            if _portable(case):
                if args.check or not (args.materialize or args.validate):
                    value = preflight_workspace_case(case, args.tracks_root, args.track)
                else:
                    if not args.curation:
                        raise ValueError("portable workspace materialization requires --curation <ai-curator.json>")
                    curation = json.loads(args.curation.read_text(encoding="utf-8"))
                    value = materialize_workspace_case(case, args.tracks_root, curation, args.track)
            elif args.check:
                value = preflight_legacy(case, args.tracks_root, args.catalog, args.track)
            else:
                value = ingest_legacy(case, args.tracks_root, args.catalog, args.track, args.materialize or args.validate, args.validate)
        elif args.command == "judge":
            results = score_frozen_run(args.run_dir); value = {"status": "completed", "results": results, "results_path": str(args.run_dir.resolve() / "results.json")}
        elif args.command == "report":
            payload = args.run_dir.resolve() / "results.json"
            workspace = payload.is_file() and isinstance(json.loads(payload.read_text(encoding="utf-8")).get("results"), list)
            path = render_workspace_report(args.run_dir, args.output) if workspace else render_report(args.run_dir, args.output)
            value = {"status": "completed", "report": str(path)}
        else:
            tool = SOURCE_ROOT / "tools" / "export_huggingface.py"
            if not tool.is_file():
                raise FileNotFoundError("export-hf is available from a source checkout; clone the repository for dataset export")
            return subprocess.run([sys.executable, str(tool), "--output", str(args.output)], cwd=SOURCE_ROOT, check=False).returncode
        _emit(args.command, value, args.json); return 0
    except (FileNotFoundError, FileExistsError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        if args.json: _json({"status": "error", "error": str(exc)})
        else: print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
