# Growing Bench

**Correct isn’t enough. Growing Bench evaluates whether an agent completed the task and whether its work justified the time, scope, and interaction cost.**

It is a living regression suite for useful, proportionate agent work: work that solves the real problem without defensive scope expansion, mean review behavior, missed high-value actions, or expensive ceremony.

![Growing Bench report preview](docs/assets/report-preview.svg)

The preview uses the checked-in four-context smoke: 96% mean task success, 92% necessary-action recall, 24 avoidable human minutes, four low-value selected actions, and one missed required action. ROI remains available as a secondary diagnostic—not the headline.

## Try it in two minutes

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing_Bench.git
cd Growing_Bench
python -m pip install -e .
python -m growing_bench smoke --output runs/first-look
```

No model call is made. Open:

- `runs/first-look/report.html` for the action-value report;
- `runs/first-look/live-adapter/report.html` for a real workspace run with checks and diff.

## A result can be correct and still be bad work

In the deterministic internal-review smoke case, the response reaches the requested decision and correctly rejects pointless extra seed runs. It also proposes broad integrity and representativeness audits without a concrete trigger. The task succeeds, but the action-level evaluation identifies two low-value actions and 24 avoidable human minutes.

That distinction is the project: preserve necessary rigor, then show which additional work changed the outcome and which work merely consumed attention.

## Who should use it

- Agent builders comparing behavior across releases.
- Skill, prompt, and plugin authors testing whether an intervention actually helps.
- Teams evaluating coding, writing, internal-review, or peer-review agents.
- Users who want to turn a frustrating interaction into a reproducible regression case.

## Run your Agent or intervention

```bash
python -m growing_bench doctor

python -m growing_bench run path/to/task.json --agent codex --output runs/codex-1
python -m growing_bench run path/to/task.json --agent claude-code --output runs/claude-1
python -m growing_bench run path/to/task.json --agent openclaw --output runs/openclaw-1

# Apply any prompt/skill text as an intervention overlay
python -m growing_bench run path/to/task.json --agent codex \
  --intervention path/to/SKILL.md --output runs/codex-with-skill
```

Every run uses a fresh fixture copy and retains the visible prompt, final response, raw output, checks, changed paths, diff, timing, and normalized `trajectory.jsonl`. Completion requires the expected baseline, passing post-checks, and no changes outside `allowed_paths`.

Codex, Claude Code, OpenClaw, and arbitrary command-line agents share the same artifact contract. See [Agent adapters](docs/AGENT_ADAPTERS.md).

## Add a failure case

```bash
python -m growing_bench init-case my-frustrating-case
python -m growing_bench ingest my-frustrating-case.md --check
python -m growing_bench ingest my-frustrating-case.md --materialize --validate
```

`--check` writes nothing. It reports missing context, observable completion criteria, provenance, publication permission, duplicates, pair metadata, and fixture readiness. Successful materialization enters a versioned track as `silver_pending`; it does not silently create a score.

You can also use the [bad-experience issue template](https://github.com/Takamatsu-Hikaru/Growing_Bench/issues/new/choose). See [Contributing](CONTRIBUTING.md) for the case contract.

## What ships in v0.1

- 34 released curated tasks across 17 scenario families: 9 matched pairs, 4 triads, and 4 standalone probes.
- Code, writing, internal review, and external peer review contexts.
- 544 public responses from two models, four interventions, and two replicates.
- 34 AI-adjudicated silver reference plans.
- Real repository and LaTeX fixtures.
- Action-level task success, necessary-action recall, missed value, avoidable cost, unnecessary actions, cheaper substitutes, and trajectory value.
- JSON/HTML reports and Hugging Face-ready export.

Canonical data and schemas live under [`data/`](data/). Stable task IDs retain their historical `staging-` prefix so existing responses and references do not break; release status is carried explicitly in task metadata.

## Evidence boundaries and current gaps

- AI consensus is a silver reference, not human gold.
- The 544 public responses are not yet a completed action-level leaderboard.
- Simulated interaction sessions and real-user experience claims are not included in v0.1.
- One post-bootstrap Markdown case is validated; no external community case is yet formally admitted and scored.
- External peer review excludes interaction-burden scoring.

The authoritative snapshot is [`CURRENT_STATE.md`](CURRENT_STATE.md). For automation, put `--json` before the command, for example `growing-bench --json doctor`.
