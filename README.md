# Growing Bench

**A living benchmark for AI behavior that is locally defensible but globally unhelpful.**

Growing Bench evaluates whether an agent got the task right **and whether its work was worth the time, scope, and interaction cost**. The first track covers defensive coding, defensive writing, mean internal review, and external peer review. Later model-specific failure modes can be appended as new, versioned tracks without rewriting old results.

The repository is standalone. ARIS and other skills are interventions you can test; they are not runtime dependencies.

## See the whole pipeline in one command

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing_Bench.git
cd Growing_Bench
python -m pip install -e .
python -m growing_bench smoke --output runs/first-look
```

The smoke makes no model calls. It recomputes an included four-context ROI sample from frozen AI-consensus labels, then runs a real editable workspace through the generic agent adapter, verifies the change, preserves the trajectory and diff, and renders HTML.

Open `runs/first-look/report.html` for the score sample and `runs/first-look/live-adapter/report.html` for the workspace run.

Check which live agents and fixture runtimes are available:

```bash
python -m growing_bench doctor
```

## Run a real task

```bash
# Codex
python -m growing_bench run path/to/task.json --agent codex --output runs/codex-1

# Claude Code
python -m growing_bench run path/to/task.json --agent claude-code --output runs/claude-1

# OpenClaw
python -m growing_bench run path/to/task.json --agent openclaw --output runs/openclaw-1
```

Each run uses a fresh copy of the fixture and retains the prompt, raw stdout/stderr, final answer, test results, changed paths, unified diff, and normalized `trajectory.jsonl`. Completion requires the expected baseline, passing completion checks, and no edits outside `allowed_paths`.

The `command` adapter supports any other agent that can be launched as a process. See [Agent adapters](docs/AGENT_ADAPTERS.md).

## Add a bad experience as a new case

Start from [`living/examples/case.md`](living/examples/case.md) or [`living/examples/code_case.md`](living/examples/code_case.md), then run:

```bash
python -m growing_bench ingest my-case.md --materialize --validate
```

Preflight checks that the goal and completion criteria are observable, provenance and publication permission are present, the case is not a duplicate, pair metadata is coherent, and the declared repository or LaTeX fixture can actually run. A passing case is added to a new track as `silver_pending`; ingestion never silently creates a benchmark score.

## What is included

- 34 canonical tasks: 10 code, 8 writing, 8 internal review, 8 external peer review.
- 17 matched groups with variants and provenance.
- 544 completed public responses: four interventions, two models, two replicates.
- 34 AI-adjudicated silver reference plans.
- Executable repository and LaTeX fixtures.
- A canonical ROI scorer measuring success, necessary-action recall, missed value, avoidable cost, unnecessary actions, and trajectory value.
- Hugging Face-ready data export via `python -m growing_bench export-hf`.

Canonical data and schemas live under `data/`. The evaluator engine is vendored here; no ARIS checkout is required. `legacy/provisional_roi_demo.py` is retained only as historical demo code and is not called by the public CLI.

## Main commands

| Command | Purpose |
|---|---|
| `growing-bench smoke` | Offline, one-command reproducibility path |
| `growing-bench run` | Execute a materialized task with an agent |
| `growing-bench judge` | Recompute a frozen evaluated run |
| `growing-bench report` | Render scored or live-run HTML |
| `growing-bench ingest` | Append a Markdown case to a versioned track |
| `growing-bench doctor` | Check installed agents and runtimes |
| `growing-bench export-hf` | Prepare a Hugging Face Dataset tree |

## Evidence boundary

The included references are AI-adjudicated silver references, not human gold. Interaction metrics from simulated sessions must be named simulated burden, correction count, takeover rate, turns-to-success, or avoidable delay—not real user satisfaction. External peer review excludes interaction-burden scoring. The bundled smoke is a reproducibility demonstration, not a leaderboard claim.

See [Contributing](CONTRIBUTING.md) to submit a case or adapter.
