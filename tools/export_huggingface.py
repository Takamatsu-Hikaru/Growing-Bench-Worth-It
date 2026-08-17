#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / "tracks" / "workspace-v0.2"
TASKS = TRACK / "tasks"
CALIBRATION = ROOT / "data" / "releases" / "workspace-v0.2-calibration"
ARTICLE = ROOT / "docs" / "LESSWRONG_DRAFT.md"
ASSETS = ROOT / "docs" / "assets"

MANAGED_OUTPUTS = (
    "README.md", "dataset_manifest.json", "assets", "data", "evaluation",
    "examples", "reports", "supplemental", "workspace_packages",
    "tasks.jsonl", "provenance.jsonl", "pairs.json", "responses.jsonl",
    "silver_reference.json",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in materialized),
        encoding="utf-8", newline="\n",
    )
    return len(materialized)


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def reset_managed_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in MANAGED_OUTPUTS:
        target = output / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def package_task(task_dir: Path, target: Path) -> list[str]:
    files = sorted(
        path for path in task_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(task_dir).as_posix()
            archive.write(path, f"{task_dir.name}/{relative}")
    return [path.relative_to(task_dir).as_posix() for path in files]


def export_workspaces(output: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = read_json(TRACK / "inventory.json")
    inventory_by_id = {row["task_id"]: row for row in inventory["tasks"]}
    task_rows: list[dict[str, Any]] = []
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task_dir in sorted(path for path in TASKS.iterdir() if path.is_dir()):
        task = read_json(task_dir / "task.json")
        metadata = inventory_by_id[task["task_id"]]
        archive_name = f"workspace_packages/{task['task_id']}.zip"
        package_files = package_task(task_dir, output / archive_name)
        fixture_files = [name for name in package_files if name.startswith("fixture/")]
        row = {
            **task,
            "scenario_family": metadata["family"],
            "variant": metadata["variant"],
            "package_maturity": metadata["package_maturity"],
            "evaluation_maturity": metadata["evaluation_maturity"],
            "workspace_type": "latex_project" if any(name.endswith(".tex") for name in fixture_files) else "code_repository",
            "workspace_archive": archive_name,
            "workspace_file_count": len(fixture_files),
            "package_file_count": len(package_files),
        }
        task_rows.append(row)
        families[metadata["family"]].append(row)

    family_rows = []
    for family, rows in sorted(families.items()):
        count = len(rows)
        family_rows.append({
            "track_id": "workspace-v0.2",
            "scenario_family": family,
            "structure": {1: "standalone", 2: "matched_pair", 3: "triad"}.get(count, "group"),
            "task_count": count,
            "contexts": sorted({row["kind"] for row in rows}),
            "variants": [row["variant"] for row in rows],
            "task_ids": [row["task_id"] for row in rows],
        })
    return task_rows, family_rows


def export_calibration(output: Path) -> dict[str, int]:
    run_card = read_json(CALIBRATION / "run-card.json")
    source_map = read_json(CALIBRATION / "source-run-map.json")["items"]
    results = read_json(CALIBRATION / "results.json")["results"]
    consensus = read_json(CALIBRATION / "consensus.json")["items"]
    result_by_item = {row["item_id"]: row for row in results}
    consensus_by_item = {row["item_id"]: row for row in consensus}
    trajectory_rows, score_rows, action_rows, reference_rows = [], [], [], []

    for mapping in source_map:
        item_id, run_name = mapping["item_id"], mapping["run_name"]
        run_dir = CALIBRATION / "trajectories" / run_name
        summary = read_json(run_dir / "summary.json")
        score = result_by_item[item_id]
        trajectory_rows.append({
            "item_id": item_id,
            "run_name": run_name,
            "task_id": mapping["task_id"],
            "model": run_card["model"],
            "adapter": run_card["adapter"],
            "release": run_card["release"],
            "status": summary["status"],
            "kind": summary["kind"],
            "title": summary["title"],
            "elapsed_seconds": summary["elapsed_seconds"],
            "changes": summary["changes"],
            "completion_criteria": summary["criterion_results"],
            "events": read_jsonl(run_dir / "trajectory.jsonl"),
            "diff": (run_dir / "changes.diff").read_text(encoding="utf-8"),
            "final_response": (run_dir / "final.md").read_text(encoding="utf-8"),
        })
        score_rows.append({key: value for key, value in score.items() if key != "actions"})
        categories = score.get("action_categories", {})
        for action in score["actions"]:
            action_rows.append({
                "item_id": item_id,
                "run_name": run_name,
                "task_id": score["task_id"],
                "domain": score["domain"],
                "task_success": score["task_success"],
                "necessary_action_recall": score["necessary_action_recall"],
                "trajectory_value": score["trajectory_value"],
                "category": categories.get(action["action_id"]),
                **action,
            })
        reference_rows.append({
            "item_id": item_id,
            "run_name": run_name,
            "task_id": mapping["task_id"],
            **consensus_by_item[item_id],
        })

    counts = {
        "calibration_trajectories": write_jsonl(output / "data" / "calibration_trajectories.jsonl", trajectory_rows),
        "calibration_scores": write_jsonl(output / "data" / "calibration_scores.jsonl", score_rows),
        "action_scores": write_jsonl(output / "data" / "action_scores.jsonl", action_rows),
        "consensus_references": write_jsonl(output / "data" / "consensus_references.jsonl", reference_rows),
    }
    for name in ("run-card.json", "evaluation-method.json", "evaluator-a.json", "evaluator-b.json", "consensus.json", "source-run-map.json"):
        copy_file(CALIBRATION / name, output / "evaluation" / name)
    copy_file(CALIBRATION / "report.html", output / "reports" / "workspace-v0.2-calibration.html")
    return counts


def export_supplemental(output: Path) -> dict[str, int]:
    target = output / "supplemental" / "static_qa"
    static_tasks = ROOT / "data" / "tasks" / "tasks.jsonl"
    static_responses = ROOT / "data" / "runs" / "public-544-v1" / "results.public.jsonl"
    files = {
        static_tasks: target / "tasks.jsonl",
        ROOT / "data" / "tasks" / "provenance.jsonl": target / "provenance.jsonl",
        ROOT / "data" / "tasks" / "pairs.json": target / "pairs.json",
        static_responses: target / "responses.jsonl",
        ROOT / "data" / "references" / "silver_reference.json": target / "silver_reference.json",
    }
    for source, destination in files.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        copy_file(source, destination)
    return {
        "static_qa_tasks": len(read_jsonl(static_tasks)),
        "static_qa_responses": len(read_jsonl(static_responses)),
    }


def dataset_card() -> str:
    metadata = """---
pretty_name: "Growing Bench: Worth It"
language:
- en
license: mit
task_categories:
- text-generation
tags:
- agents
- agent-evaluation
- benchmark
- coding-agents
- alignment
- trajectories
configs:
- config_name: workspace_tasks
  default: true
  data_files:
  - split: train
    path: data/workspace_tasks.jsonl
- config_name: scenario_families
  data_files:
  - split: train
    path: data/scenario_families.jsonl
- config_name: calibration_trajectories
  data_files:
  - split: train
    path: data/calibration_trajectories.jsonl
- config_name: calibration_scores
  data_files:
  - split: train
    path: data/calibration_scores.jsonl
- config_name: action_scores
  data_files:
  - split: train
    path: data/action_scores.jsonl
- config_name: consensus_references
  data_files:
  - split: train
    path: data/consensus_references.jsonl
- config_name: supplemental_static_tasks
  data_files:
  - split: train
    path: supplemental/static_qa/tasks.jsonl
- config_name: supplemental_static_responses
  data_files:
  - split: train
    path: supplemental/static_qa/responses.jsonl
---
"""
    article = ARTICLE.read_text(encoding="utf-8").strip()
    release_root = "https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/"
    for name in ("growing-bench-hero.png", "growing-bench-architecture.jpg", "how-growing-bench-grows.jpg"):
        article = article.replace(release_root + name, "assets/" + name)
    dataset_section = """

## Explore and use the dataset

The `workspace_tasks` configuration is the main entry point. Each row links to a complete runnable package in `workspace_packages/`. The other configurations expose scenario families, recorded trajectories, trajectory scores, action-level scores, and consensus reference actions in the Hugging Face Data Studio.

```python
from datasets import load_dataset

tasks = load_dataset(
    "takamatsu-hikaru/Growing-Bench-Worth-It",
    "workspace_tasks",
    split="train",
)
print(tasks[0]["title"])
print(tasks[0]["workspace_archive"])
```

To execute tasks, compare a prompt or skill, render the HTML report, or append a new case, use the [Growing Bench GitHub repository](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It).

| Configuration | Contents |
| --- | --- |
| `workspace_tasks` | 50 executable code, writing, internal-review, and peer-review workspaces |
| `scenario_families` | 25 matched pairs, triads, and standalone decision boundaries |
| `calibration_trajectories` | Recorded workspace events, diffs, checks, timing, and final responses |
| `calibration_scores` | Task success, necessary-action recall, avoidable cost, missed value, and trajectory value |
| `action_scores` | One row per evaluated action with category, cost, impact, and evidence-linked status |
| `consensus_references` | Machine-readable AI-consensus reference actions |
| `supplemental_static_tasks` | Earlier static QA cases |
| `supplemental_static_responses` | Earlier static QA responses for analysis and migration experiments |

## Run it locally

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It.git
cd Growing-Bench-Worth-It
python -m pip install -e .
growing-bench smoke --output runs/first-look
```

See `examples/run_one_task.md` and `examples/test_your_skill.md` in this Dataset repository for task and intervention workflows.
"""
    return metadata + article + dataset_section


def write_examples(output: Path) -> None:
    examples = {
        "load_dataset.py": '''from datasets import load_dataset

tasks = load_dataset(
    "takamatsu-hikaru/Growing-Bench-Worth-It",
    "workspace_tasks",
    split="train",
)

for row in tasks.select(range(3)):
    print(row["task_id"], row["title"], row["workspace_archive"])
''',
        "run_one_task.md": """# Run one workspace task

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It.git
cd Growing-Bench-Worth-It
python -m pip install -e .
growing-bench run tracks/workspace-v0.2/tasks/<task-id>/task.json --output runs/<task-id> --agent codex
growing-bench judge runs/<task-id> --agent codex --output runs/<task-id>/judgment.json
growing-bench report runs/<task-id> --output runs/<task-id>/report.html
```

Each `workspace_packages/<task-id>.zip` contains the matching task metadata, fixture, checks, reference solution, and adversarial solution used for package admission.
""",
        "test_your_skill.md": """# Test your prompt, skill, plugin, or harness

```bash
growing-bench self-test path/to/intervention.md --agent codex --judge codex --suite quick --strict --output runs/my-intervention
```

Growing Bench runs baseline and intervention conditions on the same workspace tasks, records the visible trajectories, evaluates actions, and writes a paired static HTML report.
""",
    }
    for name, content in examples.items():
        path = output / "examples" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the complete Growing Bench Hugging Face Dataset repository")
    parser.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    args = parser.parse_args()
    output = args.output.resolve()
    reset_managed_output(output)
    task_rows, family_rows = export_workspaces(output)
    counts = {
        "workspace_tasks": write_jsonl(output / "data" / "workspace_tasks.jsonl", task_rows),
        "scenario_families": write_jsonl(output / "data" / "scenario_families.jsonl", family_rows),
        "workspace_packages": len(list((output / "workspace_packages").glob("*.zip"))),
        **export_calibration(output),
        **export_supplemental(output),
    }
    for name in ("growing-bench-hero.png", "growing-bench-architecture.jpg", "how-growing-bench-grows.jpg"):
        copy_file(ASSETS / name, output / "assets" / name)
    (output / "README.md").write_text(dataset_card(), encoding="utf-8", newline="\n")
    write_examples(output)
    write_json(output / "dataset_manifest.json", {
        "dataset_id": "takamatsu-hikaru/Growing-Bench-Worth-It",
        "release": "0.2.0-rc1",
        "source_repository": "https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It",
        "counts": counts,
    })
    print(json.dumps({"output": str(output), "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
