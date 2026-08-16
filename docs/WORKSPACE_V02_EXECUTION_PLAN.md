# Growing Bench workspace-v0.2 execution plan

## 1. Objective

Growing Bench v0.2 will ship a living regression suite for useful,
proportionate agent work. Its core benchmark will contain 50 independently
runnable workspace tasks. Every task will require an agent to inspect and act
on a real repository, LaTeX project, or paper-and-evidence workspace. Static
prompt responses remain useful calibration data, but they are not counted as
workspace executions.

The release target is:

- 50/50 tasks with an isolated executable workspace;
- 50/50 tasks with reproducible baseline and completion checks;
- 50/50 tasks with explicit scope and artifact contracts;
- a runner that records visible multi-step activity and measured time;
- an eight-task stratified scoring slice proving the full evaluation path;
- one post-bootstrap Markdown case admitted through the growing pipeline;
- a standalone install, CLI, report, schemas, CI, and public documentation.

The current full model matrix is explicitly out of scope. It will be run later
on suitable compute. The existing 544 responses remain an auxiliary static
track and are not presented as real agent trajectories.

## 2. Non-negotiable boundaries

1. The formal workspace benchmark contains no prompt-only tasks.
2. Each published task owns an immutable fixture directory. Matched variants
   may be generated from a shared authoring template, but never share mutable
   run state.
3. An agent must inspect workspace evidence to complete a task reliably. The
   prompt must not contain the complete answer.
4. Task success comes from artifacts and checks, not an agent's claim that it
   finished.
5. Action extraction uses visible execution events as primary evidence. The
   final response is only one event in the trajectory.
6. Hidden chain-of-thought is neither requested nor stored.
7. Actual execution cost, estimated downstream cost, and proposed-but-not-run
   cost remain separate.
8. External peer review excludes user-experience scoring.
9. AI consensus is called silver or AI-adjudicated reference, never human gold.
10. Canary runs debug infrastructure. They do not substitute for building all
    50 tasks.
11. Validation stays proportional: verify user-visible behavior, executable
    checks, scope, and reproducibility. Do not add unrelated security audits,
    speculative threat models, or SHA-256 machinery unless a specific public
    artifact boundary requires immutable identity.

## 3. Tracks and corpus composition

### 3.1 Track separation

```text
tracks/
  static-response-v0.1/
  workspace-v0.2/
```

`static-response-v0.1` preserves the 34 historical scenarios, 544 responses,
and their calibration references. `workspace-v0.2` is the formal executable
benchmark. Results from the two tracks are never aggregated into one score.

### 3.2 Final 50-task composition

| Context | Existing scenarios to materialize | New tasks | Final |
|---|---:|---:|---:|
| Code | 10 | 4 | 14 |
| Writing | 8 | 4 | 12 |
| Internal review | 8 | 4 | 12 |
| External peer review | 8 | 4 | 12 |
| Total | 34 | 16 | 50 |

The current 17 scenario families remain. Eight new matched pairs bring the
total to 25 families: 17 pairs, four triads, and four standalone probes.

## 4. Per-task maturity ladder

Every task has an explicit maturity state.

| State | Requirement |
|---|---|
| T0 Scenario | A prompt or scenario exists. It is not a workspace task. |
| T1 Workspace | An isolated repository, LaTeX project, or evidence workspace exists. |
| T2 Contract | Prompt, checks, artifacts, scope, budget, provenance, and pair metadata are frozen. |
| T3 Validated | Baseline, reference completion, no-op rejection, post-check, and allowed paths are verified. |
| T4 Executed | A real agent run produced artifacts and a visible multi-step trajectory. |
| T5 Adjudicated | Reference actions, extracted actions, and dimensions have AI consensus. |
| T6 Scored | Outcome, scope, action value, cost, matched behavior, and report are reproducible. |

The 50-task corpus is considered built only at 50/50 T3. The current release
slice will take eight stratified tasks to T6. A future compute run will take the
remaining tasks through T4-T6.

## 5. L0 - Freeze public semantics and schemas

### Work

- Create the two versioned tracks.
- Freeze machine-readable schemas for task, visible trajectory, run summary,
  action, annotation, reference plan, score, and living admission.
- Publish the 50-task family and variant inventory.
- Mark the 544 historical responses as static calibration data.
- Ensure public status files never describe static responses as workspace runs.

### Exit criteria

- Static and workspace claims are unambiguous.
- Every target task has a stable context, family, variant, and environment type.
- Schemas reject prompt-only records from the workspace track.

## 6. L1 - Build the real execution and trajectory runner

### Visible event contract

The normalized trajectory supports:

```text
user
assistant_message
file_read
search
tool_call
command_start
command_result
test_result
compile_result
file_write
patch
artifact
user_interaction
final
diff
```

Each event records, where observable, an event ID, timestamp, duration, tool,
target, status, visible output, usage, and source adapter. Raw vendor logs remain
available beside the normalized trajectory.

### Runner behavior

- Copy every fixture into clean `before/` and `workspace/` directories.
- Verify the declared passing or specifically failing baseline.
- Run Codex, Claude Code, OpenClaw, or a custom command adapter.
- Retain visible tool activity, failures, retries, and recovery.
- Run post-execution checks.
- Save changed paths and a readable diff.
- Enforce allowed paths over the complete directory tree.
- Validate required artifacts and observable completion criteria.
- Distinguish completed, partial, failed, timed out, and refused runs.

### Time and cost

- Measure trajectory wall time and command/test/compile durations.
- Preserve interaction turns, corrections, retries, and waiting time.
- Use action-level actual time only when supported by event evidence.
- Keep unattributable time at trajectory level.
- Never replace missing actual time with an unlabeled estimate.

### Exit criteria

- Codex real tool events normalize into the public event contract.
- Other adapters expose supported events and mark unavailable fields honestly.
- A fluent final response cannot override failed artifacts or checks.
- A synthetic runner fixture passes without being counted as a benchmark task.

## 7. L2 - Build the workspace task factory

### Published task layout

```text
tracks/workspace-v0.2/tasks/<task_id>/
  task.json
  prompt.md
  fixture/
  checks/
  reference/
    expected_outcome.json
    reference_plan.silver.json
  provenance.json
  README.md
```

### Required contract

Every task declares:

- task, track, context, family, and variant IDs;
- fixture and required input/output artifacts;
- prompt and authorization boundary;
- baseline expectation and exact expected failure when applicable;
- executable checks;
- machine-checkable and semantic completion criteria;
- allowed, forbidden, and ignored paths;
- human, machine, compute, and interaction budgets;
- matched-group metadata;
- provenance and publication permission.

### Admission validator

The validator checks that:

- the fixture copies and runs independently;
- baseline behavior is reproducible;
- a no-op cannot pass;
- checks detect an incorrect or incomplete artifact;
- allowed paths are neither empty by mistake nor repository-wide by default;
- the prompt does not disclose the target decision;
- reliable completion requires workspace inspection;
- paired variants differ only in decision-relevant facts;
- private or unsafe material cannot enter the public fixture.

### Exit criteria

- All contexts use one contract and one validator.
- No task-specific runner branch is needed.
- A task cannot enter `workspace-v0.2` below T3.

## 8. L3 - Materialize all existing 34 scenarios

### Code: 10 tasks

Build independent repositories for `code-native`, `code-reuse`, `code-safety`,
`code-scope`, and `code-skill-fit`. Agents must inspect real code, implement the
requested change, update focused tests when needed, run checks, and leave a
verifiable diff. Existing archive and Markdown renderer fixtures are starting
assets, not completed task coverage.

### Writing: 8 tasks

Build complete LaTeX workspaces for `writing-critic`, `writing-hedges`,
`writing-limitations`, and `writing-negation`. Each contains the manuscript,
evidence notes, references, and data needed to edit real `.tex` files and compile
the result. Checks cover compilation, numeric accuracy, claim scope, authorized
files, and avoidance of unrelated rewriting.

### Internal review: 8 tasks

Provide paper text, experiment configuration, data or predictions, verification
scripts, and an internal decision gate. The output is a real `review.md` or
`decision.json` with evidence locations. The prompt alone is insufficient.

### External peer review: 8 tasks

Provide complete bounded submission packages. Agents create evidence-grounded
reviews that separate blockers, required revisions, optional work, and final
recommendation. Interaction satisfaction is not scored.

### Exit criteria

- 34/34 reach T3.
- Every task owns an independent fixture.
- Every task rejects a no-op and accepts a known-correct reference artifact.
- All matched variants retain their intended counterfactual relationship.

## 9. L4 - Add 16 equally complete matched tasks

Add four tasks in each context, organized as eight new matched pairs. Candidate
families include cache consistency, parser trust boundaries, migration-helper
reuse, protocol-wide testing, limitation visibility, causal claim strength,
deterministic versus stochastic gates, claim-threshold crossings, bounded versus
general claims, theoretical assumptions, efficiency versus state-of-the-art
claims, and optional versus necessary datasets.

Each new task follows the same T0-T3 path as an existing task. New tasks cannot
be admitted as prose-only examples.

### Exit criteria

- 50/50 tasks reach T3.
- The corpus contains 14 code, 12 writing, 12 internal-review, and 12
  external-review tasks.
- All 25 families have explicit pair, triad, or standalone semantics.

## 10. L5 - Validate the complete 50-task corpus

For every task:

```text
copy fixture
-> run baseline
-> verify expected baseline
-> apply or generate the known-correct reference artifact
-> run post-check
-> verify allowed paths
-> reset and repeat
```

Negative controls verify that a no-op, answer-only response, wrong-file change,
unsupported claim, absent evidence location, missing compilation, or inappropriate
one-size-fits-all paired behavior does not receive full completion.

This level validates the benchmark, not a model leaderboard.

### Exit criteria

- 50/50 environments are valid and reproducible.
- 50/50 reference completions pass.
- 50/50 no-op controls fail.
- 50/50 scope contracts are enforced.
- Corpus status is generated from these results.

## 11. L6 - Calibrate evaluation on eight tasks

Only after all 50 tasks reach T3, select two tasks from each context and run them
through the complete evaluation pipeline.

### Action extraction

Two independent AI evaluators extract independently choosable actions from
visible events. Tool calls and sentences are not automatically actions. Repeated
mechanical retries may be grouped while their count and elapsed cost remain
visible. A third blind evaluator merges semantic duplicates and retains genuine
disagreement as unresolved.

### Reference plan

Freeze required, optional high-value, forbidden or unnecessary, and unresolved
actions. Evaluators cannot see model identity, intervention identity, or scores.

### Dimensions

Label user request, necessity, problem and success probabilities, outcome and
decision impact, feasibility, actual or estimated time, opportunity cost, user
burden where applicable, observed result, cheaper substitute, and defensive
reason when relevant.

### Public action categories

- Necessary and efficient
- Necessary but expensive
- Avoidable
- Optional or conditional
- Proposed but not executed
- Failed or reverted
- Missed
- Unresolved

### Exit criteria

- Eight trajectories reach T6.
- Action granularity is credible under manual spot inspection.
- Necessary-but-expensive work is not mislabeled avoidable.
- Proposed future cost is not charged as actual execution cost.
- Outcome, scope, action value, time, and matched behavior recompute from public
  artifacts.

No full 50-task model matrix is run at this level.

## 12. L7 - Complete one living/growing admission

Take a new Markdown case that is not a preinstalled fixture through:

```text
Markdown
-> parse
-> AI curate
-> duplicate and pair analysis
-> fixture creation
-> task contract
-> baseline and admission validation
-> staging
-> real agent run
-> action extraction
-> AI consensus
-> score and report
-> versioned admission
```

The curator verifies observable completion, workspace sufficiency, publication
permission, duplication, pair potential, safe executability, and check quality.
Cases below T3 remain draft or staging.

### Exit criteria

- One post-bootstrap case reaches T6.
- The new case enters a new versioned track without changing old cases or scores.
- The same public CLI can ingest another case later.

## 13. L8 - Finish the open-source product

### Distribution and CLI

- Bundle runtime resources so an installed wheel runs outside the source tree.
- Keep the public commands `run`, `judge`, `report`, `ingest`, and `smoke`.
- Default to readable output and provide explicit JSON mode.
- Make errors short and actionable on Windows and Linux.

### Reporting

Lead with task success, necessary-action recall, missed value, avoidable time,
and unnecessary work. Keep ROI secondary. Show human-readable task titles,
action evidence, diffs, cheaper substitutes, matched variants, and
baseline/intervention comparison when available.

### Portability and quality

- Publish JSON schemas.
- Add offline golden event fixtures for Codex, Claude Code, and OpenClaw.
- Test source checkout and installed-wheel quickstarts in clean directories.
- Validate HTML reporting and dataset export.
- Generate one authoritative current-state file from actual artifacts.

### Documentation and launch

- Update README around one real result and a two-minute quickstart.
- Explain the static and workspace tracks honestly.
- Document how to run an agent or intervention and add a case.
- Prepare a concise engineering-oriented tech report and LessWrong launch draft.

### Exit criteria

- A clean clone or wheel install can reproduce the scored eight-task slice.
- The 50-task corpus validates locally without model calls.
- One command produces a complete offline demonstration report.
- Public claims match shipped evidence.

## 14. Authoritative completion checklist

- [x] Static and workspace tracks are separated.
- [x] Real visible-event trajectory runner is available.
- [x] Task factory and admission validator are available.
- [x] Existing 34 scenarios are workspace-backed at T3.
- [x] Sixteen new tasks are workspace-backed at T3.
- [x] All 50 tasks pass corpus validation.
- [x] Eight stratified trajectories reach T6.
- [x] One new living case reaches T6 and is admitted.
- [x] Wheel, CLI, report, schemas, adapters, CI, and docs are independently usable.
- [x] No complete 50-task model matrix is claimed or required for this milestone.

This document is the execution authority for workspace-v0.2. A successful
smoke, a large static response count, or an isolated high-quality task cannot be
used to mark a later level complete.

## RC1 freeze note (2026-08-16)

All checklist items above are complete at the stated milestone boundary: 50/50 package admission, 8/50 blind AI silver semantic calibration, one project-authored living admission, and no full 50-task model matrix claim. Package admission is not described as complete semantic evaluation.
