![Growing Bench: Worth It](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/growing-bench-hero.png)

# Growing Bench: Worth It

**Correct isn't enough. Was the work worth it?**

[Explore the 50 workspace tasks, trajectories, and action scores on Hugging Face](https://huggingface.co/datasets/takamatsu-hikaru/Growing-Bench-Worth-It)

Growing Bench runs an Agent on real disposable repositories and LaTeX projects, records what it actually did, and explains whether the work justified its time, scope, and interaction cost.

A coding Agent may finish a bounded change while also creating an unrequested SHA 256 manifest, auditing unrelated modules, and building recovery machinery for a disposable fixture. A writing Agent may turn one clear paragraph into a long list of claims the project does not prove. That happened when Codex polished this repository's README.

Growing Bench turns those experiences into repeatable tests for Agents, skills, prompts, plugins, and harnesses.

## How it works

![Growing Bench architecture](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/growing-bench-architecture.jpg)

## Test your Agent or skill

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It.git
cd Growing-Bench-Worth-It
python -m pip install -e .

growing-bench self-test examples/interventions/proportional-work.md \
  --agent codex \
  --judge codex \
  --suite quick \
  --output runs/proportional-work
```

This command runs the same four workspace tasks twice:

1. baseline Agent
2. Agent with the intervention
3. condition-blind semantic action judgment
4. deterministic scoring
5. paired HTML report, opened automatically

The report shows:

* task success
* necessary-action recall
* avoidable actions
* missed necessary actions
* observed elapsed time and tokens when the adapter exposes them
* touched files, checks, tool events, and trajectory completeness
* observed, estimated, and imputed action time as separate values
* evidence, omission consequence, and cheaper substitute for each action

Use two independent judges and a third adjudication pass for a stricter run:

```bash
growing-bench self-test examples/interventions/proportional-work.md \
  --agent codex \
  --judge codex \
  --suite balanced \
  --strict \
  --output runs/proportional-work-strict
```

Use `--context code`, `--context writing`, `--context internal_review`, or `--context external_peer_review` when an intervention targets one kind of work. `self-test --help` also documents explicit task files, output, and partial-run behavior.

The complete artifact and exit-code contract is in [docs/SELF_TEST.md](docs/SELF_TEST.md).

## See the product without model calls

```bash
growing-bench smoke --output runs/first-look
```

The offline tour recomputes scored examples, runs a small disposable workspace with the command adapter, and generates HTML. It finishes by printing the `self-test` command for your own Agent or skill.

## What the evaluator asks

Every selected action receives one primary label:

* `necessary`: omitting it would fail an explicit requirement or create an evidence-backed material risk
* `optional`: useful and dispensable
* `avoidable`: redundant, unrelated, overly broad, or replaceable by a cheaper comparable action
* `missed`: required work absent from the trajectory
* `unresolved`: evidence is insufficient or judges disagree

`necessary` requires an explicit requirement ID, a concrete omission consequence, and one atomic unit of work. Cost stays on a separate axis. Expensive required work remains `Necessary · high cost`; it never becomes waste solely because it was expensive.

The frozen judge calibration contains 20 actions across 10 decision boundaries. It covers focused versus repeated verification, bounded versus unrelated exploration, deterministic review, defensive work with and without a real trigger, required expensive work, missed actions, repeated reviews, and evidence-triggered versus speculative refactoring.

Run the current judge prompt on that calibration set:

```bash
growing-bench calibrate-judge \
  --judge codex \
  --output runs/judge-calibration
```

## Workspace tasks

The repository ships 50 executable workspace tasks across 25 scenario families:

| Context | Tasks | Agent workspace |
|---|---:|---|
| Code | 14 | repositories with focused executable checks |
| Writing | 12 | LaTeX and document projects |
| Internal review | 12 | evidence packages and decision artifacts |
| External peer review | 12 | papers, evidence, and review forms |

Each package contains a disposable fixture, observable completion criteria, an allowed modification scope, a minimal reference change, and known wrong solutions. Matched situations place similar behavior on opposite sides of a decision boundary.

Run one task directly:

```bash
growing-bench run tracks/workspace-v0.2/tasks/<task-id>/task.json \
  --agent claude-code \
  --output runs/claude-task
```

Built-in adapters support Codex, Claude Code, OpenClaw, and arbitrary command-line Agents.

## Trajectory quality across Agents

All adapters map visible work into a common event contract covering commands, results, reads, writes, tool calls, messages, duration, and exit status. Every run reports which events the adapter exposes and a trajectory completeness score. Missing telemetry stays visible.

Growing Bench creates a fresh fixture copy and starts the Agent process inside that workspace. Codex also receives its native `workspace-write` sandbox flag. Growing Bench does not claim a container, virtual machine, or enforced network sandbox for every adapter.

`--isolation copy` records the portable workspace-copy boundary. `--isolation agent-native` requires a supported native sandbox and currently works with Codex; unsupported adapters fail before the run starts.

See [the adapter guide](docs/AGENT_ADAPTERS.md) and [the event contract](docs/ADAPTER_EVENT_CONTRACT.md).

## Append your own bad experience

After a self-test, turn the most useful failure into a portable draft:

```bash
growing-bench append runs/proportional-work \
  --title "Agent repeated the full test suite" \
  --redact \
  --check \
  --output my-agent-case
```

`append` carries forward the runnable workspace, task, trajectory, judge output, baseline/intervention context, and minimal successful change. It checks for credentials and damaged text. Publication permission remains an explicit choice.

You can also start a case manually:

```bash
growing-bench init-case my-agent-case
growing-bench ingest my-agent-case/case.md --check
```

Preflight reports the exact file and issue, whether local use still works, and the next edit needed for public admission. Accepted cases enter a new versioned track and keep older tracks reproducible.

## How the benchmark grows

![How Growing Bench grows](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/how-growing-bench-grows.jpg)


## Main commands

```text
growing-bench self-test        compare baseline and intervention
growing-bench append           turn a run into a living-case draft
growing-bench run              execute one workspace task
growing-bench calibrate-judge  test the current judge prompt
growing-bench ingest           check or materialize a portable case
growing-bench judge            recompute canonical scores
growing-bench report           generate HTML
growing-bench smoke            run the offline product tour
growing-bench doctor           inspect local Agent CLIs
```

## Contribute

The strongest case is a small runnable workspace that preserves a frustrating decision. Include the task the Agent saw, the visible trajectory, an observable completion check, the allowed scope, and the smallest change that succeeds.

See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed.
