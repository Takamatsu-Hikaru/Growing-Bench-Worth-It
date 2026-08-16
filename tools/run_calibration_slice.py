from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from growing_bench.execution import run_task


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tracks" / "workspace-v0.2" / "tasks"
RUNS = ROOT / "runs" / "workspace-v0.2-calibration"
PROPOSAL_AGENT = ROOT / "tools" / "codex_proposal_agent.py"


SLICE = [
    ("code-gzip-rc1", "workspace-v0.2--code-native--built-in-gzip-sufficient", ["src/archive.py"]),
    ("code-untrusted-parser-rc1", "workspace-v0.2--code-parser--untrusted-upload", ["src/upload.py"]),
    ("writing-fixed-observation-rc1", "workspace-v0.2--writing-hedges--complete-fixed-set-observation", ["sections/target.tex"]),
    ("writing-population-estimate-rc1", "workspace-v0.2--writing-hedges--sample-based-population-estimate", ["sections/target.tex"]),
    ("internal-deterministic-rc1", "workspace-v0.2--review-seeds--deterministic-execution", ["review.json"]),
    ("internal-stochastic-rc1", "workspace-v0.2--review-seeds--stochastic-execution", ["review.json"]),
    ("external-bounded-extra-data-rc1", "workspace-v0.2--review-extra-experiment--irrelevant-extra-dataset", ["review.json"]),
    ("external-causal-claim-rc1", "workspace-v0.2--review-mechanism--causal-intervention", ["review.json"]),
]


def execute(row: tuple[str, str, list[str]], model: str) -> dict[str, object]:
    run_name, task_id, allowed = row
    output = RUNS / run_name
    summary_path = output / "summary.json"
    if summary_path.is_file():
        value = json.loads(summary_path.read_text(encoding="utf-8"))
        return {"run": run_name, "task_id": task_id, "status": value["status"], "reused": True}
    template = [
        "python", str(PROPOSAL_AGENT), "--prompt-file", "{prompt_file}",
        "--raw-output", str(output / "child-codex.raw.log"), "--model", model,
    ]
    for path in allowed:
        template.extend(["--allowed", path])
    value = run_task(
        TASKS / task_id / "task.json", output, model=model, reasoning="high",
        timeout=900, agent="command", command_template=json.dumps(template),
    )
    return {
        "run": run_name, "task_id": task_id, "status": value["status"],
        "post_checks_passed": value.get("post_checks_passed"),
        "allowed_paths_ok": value.get("allowed_paths_ok"),
        "elapsed_seconds": value.get("elapsed_seconds"), "reused": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 2))) as pool:
        futures = {pool.submit(execute, row, args.model): row for row in SLICE}
        for future in as_completed(futures):
            value = future.result()
            results.append(value)
            print(json.dumps(value, ensure_ascii=False), flush=True)
    results.sort(key=lambda row: str(row["run"]))
    (RUNS / "slice.run-card.json").write_text(
        json.dumps({
            "schema_version": "growing-bench-calibration-slice-1.0",
            "model": args.model, "adapter": "codex-read-only-proposal-plus-allowed-host-executor",
            "full_model_matrix": False, "task_count": len(results), "runs": results,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
