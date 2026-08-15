#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the public benchmark slice for Hugging Face Datasets")
    parser.add_argument("--output", type=Path, default=Path("dist/huggingface"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = {
        ROOT / "data/tasks/tasks.jsonl": output / "tasks.jsonl",
        ROOT / "data/tasks/provenance.jsonl": output / "provenance.jsonl",
        ROOT / "data/tasks/pairs.json": output / "pairs.json",
        ROOT / "data/runs/public-544-v1/results.public.jsonl": output / "responses.jsonl",
        ROOT / "data/references/silver_reference.json": output / "silver_reference.json",
    }
    for source, target in files.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copyfile(source, target)
    card = """---
pretty_name: Growing Bench
language:
- en
license: mit
task_categories:
- text-generation
tags:
- agents
- evaluation
- benchmark
---

# Growing Bench

This export contains 34 tasks, matched-pair metadata, provenance, 544 public
responses, and the frozen AI-consensus silver reference. Code and the canonical
scorer live in the linked GitHub repository. Silver annotations are not human gold.
"""
    (output / "README.md").write_text(card, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

