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
from .calibration import run_live_calibration
from .execution import run_task
from .health import doctor
from .ingest_experience import enrich_preflight
from .interactive import run_interactive_scenario
from .interactive_self_test import render_interactive_report, run_interactive_self_test
from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_SMOKE_SOURCE, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT, SOURCE_ROOT
from .pipeline import ingest as ingest_legacy, preflight as preflight_legacy
from .reporting import render_report
from .run_append import append_run
from .scoring import score_frozen_run
from .self_test import SUITES, render_paired_report, run_self_test
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
        print("NEXT Test your own skill: growing-bench self-test path/to/SKILL.md --agent codex --suite quick --output runs/my-skill")
    elif command == "run":
        ok = value.get("status") in {"completed", "completed_pending_judgment"}
        print(f"{'OK' if ok else 'FAIL'} Run {value.get('status')}: {value.get('task_id')}")
        print(f"  completion checks: {'pass' if value.get('post_checks_passed') else 'fail'}")
        print(f"  allowed scope: {'pass' if value.get('allowed_paths_ok') else 'fail'}")
        print(f"  trajectory: {value.get('artifacts', {}).get('trajectory', '-')}")
    elif command == "interact":
        ok = value.get("status") in {"completed", "completed_pending_judgment"}
        print(f"{'OK' if ok else 'FAIL'} Interactive run {value.get('status')}: {value.get('scenario_id')}")
        print(f"  turns: {value.get('turn_count', 0)}/{value.get('planned_turn_count', 0)}")
        print(f"  persistent session: {value.get('session_persistence') or 'unavailable'}")
        print(f"  trajectory: {value.get('artifacts', {}).get('trajectory', '-')}")
    elif command == "self-test":
        baseline = value["summary"]["baseline"]
        intervention = value["summary"]["intervention"]
        print(f"{'OK' if value['status'] == 'completed' else 'FAIL'} Self-test {value['status']}")
        left = "n/a" if baseline["task_success"] is None else f"{baseline['task_success']:.2f}"
        right = "n/a" if intervention["task_success"] is None else f"{intervention['task_success']:.2f}"
        print(f"  task success: {left} -> {right}")
        if value.get("schema_version") == "growing-bench-interactive-self-test-results-1.0":
            print(f"  state update: {baseline['state_update_success']} -> {intervention['state_update_success']}")
            print(f"  stale narrative events: {baseline['stale_narrative_events']} -> {intervention['stale_narrative_events']}")
            print(f"  scenario pressure: {baseline['scenario_pressure_points']} -> {intervention['scenario_pressure_points']}")
            print(f"  observed Agent burden: {baseline['observed_agent_burden_points']} -> {intervention['observed_agent_burden_points']}")
        else:
            print(f"  avoidable actions: {baseline['avoidable_action_count']} -> {intervention['avoidable_action_count']}")
            print(f"  missed necessary: {baseline['missed_necessary_count']} -> {intervention['missed_necessary_count']}")
        print(f"  report: {value['report']}")
        if value["failures"]:
            print(f"  failed stages: {len(value['failures'])}")
    elif command == "calibrate-judge":
        print(f"{'OK' if value['failed'] == 0 else 'FAIL'} Judge calibration {value['passed']}/{value['case_count']}")
        print(f"  prompt: {value['prompt_version']}")
    elif command == "append":
        print(f"{'OK' if value['status'] == 'ready_for_curation' else 'WARN'} Appended case: {value['status']}")
        print(f"  case: {value['case']}")
        if value["issues"]:
            for issue in value["issues"]:
                print(f"  {issue['code']}: {issue['path']} | {issue['next_step']}")
    elif command in {"check", "ingest"}:
        status = value.get("status") or value.get("candidate", {}).get("status") or value.get("ingest", {}).get("status")
        ok = status in {"ready_for_ai_curation", "ready_for_materialization", "validated"}
        print(f"{'OK' if ok else 'WARN'} {status}")
        issues = value.get("issues") or value.get("candidate", {}).get("issues") or []
        for issue in issues:
            print(f"  {issue.get('path', 'case.md')}: {issue['message']}")
            print(f"    Next: {issue['next_step']}")
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
    smoke = sub.add_parser("smoke", help="run the offline score and real-workspace demo")
    smoke.add_argument("--output", type=Path, default=Path("runs/smoke")); smoke.add_argument("--source", type=Path, default=DEFAULT_SMOKE_SOURCE)
    run = sub.add_parser("run", help="run one materialized workspace task")
    run.add_argument("task", type=Path); run.add_argument("--output", type=Path, required=True); run.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex"); run.add_argument("--model"); run.add_argument("--reasoning", default="high"); run.add_argument("--timeout-seconds", type=float, default=1200); run.add_argument("--intervention", type=Path); run.add_argument("--command-template"); run.add_argument("--isolation", choices=("copy", "agent-native"), default="copy", help="fresh workspace copy, or require the adapter's native sandbox")
    interact = sub.add_parser("interact", help="run one persistent multi-turn Agent scenario in a real workspace")
    interact.add_argument("scenario", type=Path); interact.add_argument("--output", type=Path, required=True); interact.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex"); interact.add_argument("--model"); interact.add_argument("--reasoning", default="high"); interact.add_argument("--timeout-seconds", type=float, default=1200); interact.add_argument("--intervention", type=Path); interact.add_argument("--command-template"); interact.add_argument("--user-mode", choices=("scripted", "simulated"), default="scripted"); interact.add_argument("--user-agent", choices=BUILTIN_AGENTS, default="codex"); interact.add_argument("--user-model"); interact.add_argument("--user-reasoning", default="medium"); interact.add_argument("--user-command-template")
    selftest = sub.add_parser("self-test", help="compare one Agent with and without a skill or intervention")
    selftest.add_argument("--mode", choices=("workspace", "interactive"), default="workspace", help="single-turn workspace tasks or persistent multi-turn scenarios"); selftest.add_argument("--scenario", type=Path, action="append", dest="scenarios", help="explicit interactive scenario JSON; repeat to replace the built-in suite"); selftest.add_argument("--user-mode", choices=("scripted", "simulated"), default="scripted"); selftest.add_argument("--user-agent", choices=BUILTIN_AGENTS, default="codex"); selftest.add_argument("--user-model"); selftest.add_argument("--user-reasoning", default="medium"); selftest.add_argument("--user-command-template")
    selftest.add_argument("intervention", type=Path, help="skill, prompt, or intervention file to compare against baseline"); selftest.add_argument("--agent", choices=BUILTIN_AGENTS, default="codex", help="Agent that runs both baseline and intervention tasks"); selftest.add_argument("--judge", choices=BUILTIN_AGENTS, default="codex", help="condition-blind LLM action evaluator"); selftest.add_argument("--suite", choices=sorted(SUITES), default="quick", help="quick runs 4 contexts; balanced runs 4 matched boundaries"); selftest.add_argument("--context", choices=("code", "writing", "internal_review", "external_peer_review"), action="append", dest="contexts", help="run only this task context; repeat to combine contexts"); selftest.add_argument("--task", type=Path, action="append", dest="tasks", help="explicit task.json; repeat to replace the built-in suite"); selftest.add_argument("--output", type=Path, required=True, help="new directory for runs, judgments, results, and paired HTML"); selftest.add_argument("--model"); selftest.add_argument("--judge-model"); selftest.add_argument("--reasoning", default="high"); selftest.add_argument("--judge-reasoning", default="high"); selftest.add_argument("--timeout-seconds", type=float, default=1200); selftest.add_argument("--command-template"); selftest.add_argument("--judge-command-template"); selftest.add_argument("--strict", action="store_true", help="use two blind judges and a third adjudicator on disagreement"); selftest.add_argument("--allow-partial", action="store_true", help="keep partial results and return success when at least one score exists"); selftest.add_argument("--no-open", action="store_true", help="do not open the paired HTML report"); selftest.add_argument("--isolation", choices=("copy", "agent-native"), default="copy", help="fresh workspace copy, or require the adapter's native sandbox")
    calibrate = sub.add_parser("calibrate-judge", help="run the current LLM judge on frozen decision boundaries")
    calibrate.add_argument("--judge", choices=BUILTIN_AGENTS, default="codex", help="Agent CLI used as the semantic judge")
    calibrate.add_argument("--output", type=Path, required=True, help="new directory for packets, raw judge outputs, and results")
    calibrate.add_argument("--model", help="optional judge model override")
    calibrate.add_argument("--reasoning", default="high", help="judge reasoning effort")
    calibrate.add_argument("--timeout-seconds", type=float, default=1200)
    calibrate.add_argument("--command-template", help="JSON command array when --judge command is used")
    calibrate.add_argument("--case", action="append", dest="cases", help="run one calibration case; repeat to tune a failed subset")
    init = sub.add_parser("init-case", help="create a portable Markdown + workspace case"); init.add_argument("name"); init.add_argument("--output", type=Path)
    add = sub.add_parser("ingest", help="preflight or materialize a Markdown case"); add.add_argument("case", type=Path); add.add_argument("--track"); add.add_argument("--tracks-root", type=Path, default=DEFAULT_TRACKS_ROOT); add.add_argument("--catalog", type=Path, default=DEFAULT_FIXTURE_CATALOG); add.add_argument("--check", action="store_true"); add.add_argument("--materialize", action="store_true"); add.add_argument("--validate", action="store_true"); add.add_argument("--curation", type=Path, help="AI curator JSON required for portable workspace materialization")
    append = sub.add_parser("append", help="turn a self-test run into a portable living-case draft")
    append.add_argument("run_dir", type=Path); append.add_argument("--title", required=True); append.add_argument("--output", type=Path, required=True); append.add_argument("--source-run"); append.add_argument("--redact", action="store_true"); append.add_argument("--check", action="store_true"); append.add_argument("--permission-to-publish", action="store_true"); append.add_argument("--tracks-root", type=Path)
    judge = sub.add_parser("judge", help="recompute scores from frozen evaluator ledgers"); judge.add_argument("run_dir", type=Path)
    report = sub.add_parser("report", help="render a scored or live run as HTML"); report.add_argument("run_dir", type=Path); report.add_argument("--output", type=Path)
    export = sub.add_parser("export-hf", help="prepare a Hugging Face Dataset repository"); export.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    return parser


def main() -> int:
    _configure_output(); parser = build_parser(); args = parser.parse_args()
    try:
        if args.command == "doctor":
            value = doctor()
        elif args.command == "smoke":
            value = _product_smoke(args.output, args.source)
        elif args.command == "run":
            value = run_task(args.task, args.output, args.model, args.reasoning, args.timeout_seconds, args.agent, args.intervention, args.command_template, args.isolation)
        elif args.command == "interact":
            value = run_interactive_scenario(
                args.scenario, args.output, agent=args.agent, model=args.model,
                reasoning=args.reasoning, timeout=args.timeout_seconds,
                intervention=args.intervention, command_template=args.command_template,
                user_mode=args.user_mode, user_agent=args.user_agent,
                user_model=args.user_model, user_reasoning=args.user_reasoning,
                user_command_template=args.user_command_template,
            )
        elif args.command == "self-test":
            if args.mode == "interactive":
                value = run_interactive_self_test(
                    args.intervention, args.output, suite=args.suite, scenario_paths=args.scenarios,
                    agent=args.agent, judge=args.judge, model=args.model, judge_model=args.judge_model,
                    reasoning=args.reasoning, judge_reasoning=args.judge_reasoning,
                    timeout=args.timeout_seconds, command_template=args.command_template,
                    judge_command_template=args.judge_command_template, strict=args.strict,
                    allow_partial=args.allow_partial, open_report=not args.no_open,
                    user_mode=args.user_mode, user_agent=args.user_agent, user_model=args.user_model,
                    user_reasoning=args.user_reasoning, user_command_template=args.user_command_template,
                )
            else:
                value = run_self_test(
                    args.intervention, args.output, suite=args.suite, task_paths=args.tasks, contexts=args.contexts,
                    agent=args.agent, judge=args.judge, model=args.model, judge_model=args.judge_model,
                    reasoning=args.reasoning, judge_reasoning=args.judge_reasoning,
                    timeout=args.timeout_seconds, command_template=args.command_template,
                    judge_command_template=args.judge_command_template, strict=args.strict,
                    allow_partial=args.allow_partial, open_report=not args.no_open, isolation=args.isolation,
                )
        elif args.command == "calibrate-judge":
            value = run_live_calibration(args.output, judge=args.judge, model=args.model, reasoning=args.reasoning, timeout=args.timeout_seconds, command_template=args.command_template, case_ids=args.cases)
        elif args.command == "init-case":
            value = _init_case(args.name, args.output)
        elif args.command == "ingest":
            case = args.case.resolve()
            try:
                case.read_text(encoding="utf-8")
                valid_utf8 = True
            except UnicodeDecodeError:
                valid_utf8 = False
            if not valid_utf8:
                value = enrich_preflight({"status": "needs_curation", "missing": [], "checks": {}}, case)
            elif _portable(case):
                if args.check or not (args.materialize or args.validate):
                    value = enrich_preflight(preflight_workspace_case(case, args.tracks_root, args.track), case)
                else:
                    if not args.curation:
                        raise ValueError("portable workspace materialization requires --curation <ai-curator.json>")
                    curation = json.loads(args.curation.read_text(encoding="utf-8"))
                    value = materialize_workspace_case(case, args.tracks_root, curation, args.track)
            elif args.check:
                value = enrich_preflight(preflight_legacy(case, args.tracks_root, args.catalog, args.track), case)
            else:
                value = ingest_legacy(case, args.tracks_root, args.catalog, args.track, args.materialize or args.validate, args.validate)
        elif args.command == "append":
            value = append_run(args.run_dir, args.output, args.title, source_run=args.source_run, redact=args.redact, check=args.check, permission_to_publish=args.permission_to_publish, tracks_root=args.tracks_root)
        elif args.command == "judge":
            results = score_frozen_run(args.run_dir); value = {"status": "completed", "results": results, "results_path": str(args.run_dir.resolve() / "results.json")}
        elif args.command == "report":
            payload = args.run_dir.resolve() / "results.json"
            result_payload = json.loads(payload.read_text(encoding="utf-8")) if payload.is_file() else {}
            if result_payload.get("schema_version") == "growing-bench-interactive-self-test-results-1.0":
                path = render_interactive_report(result_payload, args.output.resolve() if args.output else args.run_dir.resolve() / "report.html")
            elif result_payload.get("schema_version") == "growing-bench-self-test-results-1.0":
                path = render_paired_report(result_payload, args.output.resolve() if args.output else args.run_dir.resolve() / "report.html")
            elif isinstance(result_payload.get("results"), list):
                path = render_workspace_report(args.run_dir, args.output)
            else:
                path = render_report(args.run_dir, args.output)
            value = {"status": "completed", "report": str(path)}
        else:
            tool = SOURCE_ROOT / "tools" / "export_huggingface.py"
            if not tool.is_file():
                raise FileNotFoundError("export-hf is available from a source checkout; clone the repository for dataset export")
            return subprocess.run([sys.executable, str(tool), "--output", str(args.output)], cwd=SOURCE_ROOT, check=False).returncode
        _emit(args.command, value, args.json)
        if args.command in {"run", "interact"} and value.get("status") not in {"completed", "completed_pending_judgment"}:
            return 1
        if args.command == "calibrate-judge" and value.get("failed"):
            return 3
        if args.command == "self-test" and value.get("status") != "completed":
            if args.allow_partial and value.get("results"):
                return 0
            return 3 if any(row.get("stage") == "judge" for row in value.get("failures", [])) else 1
        return 0
    except (FileNotFoundError, FileExistsError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        if args.json:
            _json({"status": "error", "error": str(exc)})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
