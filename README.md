# Growing Bench

**Correct isn't enough. Growing Bench measures whether an agent's work was worth it.**

Growing Bench is a living regression suite for useful, proportionate agent work. Every workspace task asks an agent to operate on a disposable repository or LaTeX package, records what it actually did, verifies the result, and separates necessary work from avoidable work.

It is designed for the failure mode many agent benchmarks miss: the task may pass, yet the agent duplicated an existing helper, expanded scope, demanded irrelevant experiments, buried a clear claim in caveats, or consumed attention without changing the outcome.

## See it in two minutes

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing_Bench.git
cd Growing_Bench
python -m pip install -e .
growing-bench smoke --output runs/first-look
```

The smoke is offline: it makes no model calls. It recomputes four frozen action-value examples, executes one real disposable workspace task, records a normalized trajectory, and writes two static HTML reports.

The built wheel supports the same command from an empty directory. After the package is published, the install is:

```bash
python -m pip install growing-bench
growing-bench smoke --output first-look
```

## What v0.2-rc1 contains

- **50 package-admitted workspace tasks** in 25 scenario families.
- **14 code, 12 writing, 12 internal-review, and 12 external-peer-review tasks.**
- An independent fixture and reference solution for every task; code tasks are executable repositories and writing/review tasks are compilable LaTeX/evidence packages.
- Baseline, no-op, reference-solution, path-scope, semantic-oracle-leakage, and known-wrong-solution admission checks for all 50 packages.
- A real trajectory runner for Codex, Claude Code, OpenClaw, and arbitrary command-line agents.
- A canonical action-value scorer and an **8-task stratified calibration slice** with two blind AI evaluators plus a third AI adjudicator.
- One post-bootstrap Markdown case that completed the full living pipeline and entered a new immutable track.

The old 34-task/544-response collection is retained as `static-response-v0.1`. It is useful auxiliary QA data, but it is not presented as workspace execution or as a completed leaderboard.

Current verification is **25/25 public CI tests** and **232/232 local extended regressions**. The extended suite includes ignored pre-release development tests and is not presented as part of a clean clone.

## What the report tells you

Growing Bench keeps the primary signals separate:

- task success;
- necessary-action recall;
- missed high-value actions;
- avoidable or failed actions;
- observed/estimated machine time;
- avoidable human time and interaction burden when applicable;
- cheaper substitutes;
- trajectory value and ROI as secondary diagnostics.

Actions are shown as `necessary / efficient`, `necessary / expensive`, `avoidable`, `optional / conditional`, `proposed, not executed`, `failed / reverted`, `missed`, or `unresolved`. A negative number is never relabeled as "bad work" without preserving the action's role.

## Run an Agent or skill

```bash
growing-bench doctor

growing-bench run tracks/workspace-v0.2/tasks/<task-id>/task.json \
  --agent codex --output runs/codex-1

growing-bench run tracks/workspace-v0.2/tasks/<task-id>/task.json \
  --agent claude-code --intervention path/to/SKILL.md \
  --output runs/claude-with-skill

growing-bench report data/releases/workspace-v0.2-calibration
```

Each run uses a fresh fixture copy. The public run artifact retains the prompt, visible agent events, final response, checks, diff, changed paths, timing, and normalized `trajectory.jsonl`. Passing checks alone is insufficient: modifications must stay inside the declared scope, and semantic criteria remain pending until blind judging.

Agent contracts and event examples are documented in [docs/AGENT_ADAPTERS.md](docs/AGENT_ADAPTERS.md). CI tests recorded Codex, Claude Code, and OpenClaw event streams without paid model calls.

## Add a real failure case

```bash
growing-bench init-case my-frustrating-case
# Put the initial repo/LaTeX package in fixture/ and the minimal solution in reference/.
growing-bench ingest my-frustrating-case/case.md --check
```

Portable cases carry their own workspace. Preflight checks information sufficiency, observable completion, provenance, publication permission, duplicate risk, pairability, fixture presence, and executability. Materialization requires an explicit AI-curator JSON instead of pretending that a Markdown prompt is already a benchmark task:

```bash
growing-bench ingest my-frustrating-case/case.md \
  --materialize --validate --curation my-frustrating-case/curation.ai.json
```

The repository includes one complete example at `living/contributions/cli-slug-helper/`. Its path is:

`Markdown ->deterministic preflight ->independent AI curation ->staging ->workspace validation ->real Agent run ->blind AI action consensus ->canonical score ->immutable track registry`

Old tracks and scores are not rewritten when a new failure mode arrives.

## Public boundaries

- All 50 packages pass admission; only eight currently have blind AI silver semantic evaluation and scores; a full 50-task x model matrix is intentionally not included in this release.
- The 8 scored trajectories calibrate the end-to-end evaluation pipeline; they are not a model ranking.
- AI consensus is a silver reference, not human gold.
- External peer review excludes user-burden scoring.
- The shipped living case is project-authored. External community cases are the next product milestone.
- No claim of real-user satisfaction is made.

The authoritative generated snapshot is [CURRENT_STATE.md](CURRENT_STATE.md). The execution design is in [docs/WORKSPACE_V02_EXECUTION_PLAN.md](docs/WORKSPACE_V02_EXECUTION_PLAN.md), and the engineering report is in [docs/TECH_REPORT.md](docs/TECH_REPORT.md).

## Main commands

```text
growing-bench run       run one real workspace task
growing-bench judge     recompute scores from frozen evaluator ledgers
growing-bench report    generate a static HTML report
growing-bench ingest    add a portable living case
growing-bench smoke     run the one-command offline product tour
```

MIT licensed. Contributions should include publication permission and a disposable fixture without real credentials or private data.
