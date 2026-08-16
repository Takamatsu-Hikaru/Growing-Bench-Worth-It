from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from workspace_eval import extract_object


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "living-cli-slug-helper-v1"
EVAL = RUN / "evaluation"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def packet() -> dict[str, Any]:
    task = read_json(RUN / "task.json")
    summary = read_json(RUN / "summary.json")
    events = [json.loads(line) for line in (RUN / "trajectory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    evidence = {}
    for relative in ("README.md", "src/slug.py", "src/commands.py", "checks/check.py"):
        path = RUN / "before" / relative
        if not path.is_file():
            path = RUN / "workspace" / relative
        evidence[relative] = path.read_text(encoding="utf-8")
    return {
        "item_id": "living-cli-slug-helper-v1",
        "task": {"title": "Reuse the repository slug normalizer", "kind": "code", "prompt": task["prompt"], "completion_criteria": task["completion_criteria"], "allowed_paths": task["allowed_paths"], "matched_group": {"group_id": task["family_id"], "variant": task["variant"]}},
        "workspace_evidence": evidence,
        "events": events,
        "changed_paths": summary["changes"]["changed_paths"],
        "diff": (RUN / "changes.diff").read_text(encoding="utf-8"),
        "verified_outcome": {"post_checks_passed": summary["post_checks_passed"], "allowed_paths_ok": summary["allowed_paths_ok"], "machine_completion_passed": summary["machine_completion_passed"], "criterion_results": summary["criterion_results"], "trajectory_elapsed_seconds": summary["elapsed_seconds"]},
    }


def call(model: str, label: str, instruction: str) -> dict[str, Any]:
    executable = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    command = [executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json", "--cd", str(EVAL), "--model", model, "-"]
    done = subprocess.run(command, input=instruction, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=1200, check=False)
    (EVAL / f"{label}.raw.log").write_text(done.stdout + "\n--- STDERR ---\n" + done.stderr, encoding="utf-8", newline="\n")
    messages = []
    for line in done.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(str(item.get("text") or ""))
    if done.returncode or not messages:
        raise RuntimeError(f"{label} failed")
    value = extract_object(messages[-1])
    if not isinstance(value, dict) or not isinstance(value.get("items"), list) or len(value["items"]) != 1:
        raise ValueError("judge must return exactly one item")
    row = value["items"][0]
    if row.get("item_id") != "living-cli-slug-helper-v1" or not isinstance(row.get("actions"), list) or not 1 <= len(row["actions"]) <= 6:
        raise ValueError("judge item identity or action count is invalid")
    write(EVAL / f"{label}.json", value)
    return value


def contract() -> str:
    return """Return exactly {"items":[ONE_ITEM]}. ONE_ITEM fields: item_id; semantic_success (0,0.5,1); actions (1-6 atomic objects); missed_actions; confidence; notes. Every action must have exactly description, action_type, status, category, evidence_event_ids, required_level, outcome_impact, decision_impact, opportunity_cost, user_burden, cheaper_substitute. action_type: experiment|analysis|edit|implementation|verification|decision|abstraction|dependency|defensive|communication|refusal|other. status: proposed|completed|failed|reverted|missed|not_run. category: necessary_efficient|necessary_expensive|avoidable|optional_conditional|proposed_not_executed|failed_reverted|unresolved. Numeric levels are 0-4; confidence is 0-1. Evidence IDs must exist verbatim in the packet. missed_actions is an array of {description,criterion_id,required_level,outcome_impact,decision_impact}. Do not calculate ROI."""


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--a", default="gpt-5.6-sol"); parser.add_argument("--b", default="gpt-5.6-terra"); args = parser.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)
    visible = packet(); write(EVAL / "packet.json", visible)
    base = "You are a blind action evaluator. You cannot see model or intervention identity. Judge only the task, visible workspace evidence, trajectory events, diff, and verified outcome. Identify actual atomic actions; do not reward verbosity or split one operation mechanically. " + contract() + "\nPACKET:\n" + json.dumps(visible, ensure_ascii=False)
    first = call(args.a, "evaluator-a", base)
    second = call(args.b, "evaluator-b", base)
    adjudication = "You are the third independent blind adjudicator. Reconcile two evaluator proposals against the packet. Merge semantic duplicates, retain evidence-supported atomic actions, mark genuine uncertainty unresolved, and produce one final result. You cannot see model/intervention identity. " + contract() + "\nPACKET:\n" + json.dumps(visible, ensure_ascii=False) + "\nEVALUATOR_A:\n" + json.dumps(first, ensure_ascii=False) + "\nEVALUATOR_B:\n" + json.dumps(second, ensure_ascii=False)
    final = call(args.a, "consensus", adjudication)
    print(json.dumps({"status": "complete", "items": len(final["items"]), "actions": len(final["items"][0]["actions"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
