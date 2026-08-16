# Growing Bench v0.2-rc1: Correct is not enough

## 1. The product problem

Most agent evaluations ask whether the final answer or test passed. Users also care whether the agent chose work proportionate to the actual task. A response can be correct while the trajectory duplicates an existing abstraction, performs irrelevant audits, widens a bounded claim into an impossible research program, or forces the user to manage the agent.

Growing Bench turns those experiences into executable regression tests. Its intended identity is an agent engineering and evaluation tool, not a claim that a single scalar solves alignment.

## 2. Three representative contrasts

### Reuse versus reinvention

A code repository may already expose the helper needed by a one-file change. Reusing it and running the focused test is high-value work. Implementing a parallel policy, adding a framework, or modifying unrelated modules can still pass while increasing maintenance cost.

### Bounded evidence versus automatic “more experiments”

An external reviewer should distinguish evidence that supports a deliberately bounded claim from evidence needed for a broader claim. Extra datasets are valuable when they can change the stated conclusion; they are avoidable when the paper does not assert that broader generality. The benchmark therefore evaluates the assessment, the publication decision, and optional future work as separate actions.

### Necessary caution versus defensive ceremony

Input controlled by an attacker can justify validation and containment that would be wasteful in a trusted, fixed-input repository task. Matched families keep the requested operation similar while varying the evidence that changes the value of defensive work.

## 3. What is measured

The primary report keeps outcome and process distinct:

1. task success;
2. necessary-action recall;
3. missed high-value actions;
4. avoidable/failed action rate;
5. observed or estimated cost;
6. cheaper substitute;
7. interaction burden when the context represents a user interaction.

The canonical scorer derives trajectory value and ROI from those components. ROI is useful for comparison and diagnosis, but it is deliberately secondary because one ratio can hide whether a run failed, missed the goal, or merely spent too much.

## 4. A real workspace task

Each `workspace-v0.2` task is a package with:

- a task contract;
- an isolated initial fixture;
- an executable completion check;
- allowed and ignored paths;
- an exact failing-baseline signature when applicable;
- a minimal reference solution;
- matched-family metadata and provenance.

The runner copies the fixture, verifies the baseline, starts the chosen Agent, streams visible events, applies normal repository checks, records the diff and scope, and leaves semantic criteria pending for blind evaluation. It does not convert a fluent final response into task success.

## 5. Action value and AI consensus

The calibration pipeline blinds evaluator packets to model and intervention identity. Two independent AI evaluators propose atomic actions and fine-grained dimensions. A third AI adjudicator merges semantic duplicates, rejects unsupported actions, and preserves unresolved cases. The deterministic scorer then computes metrics; the judging model does not directly announce an ROI.

The action vocabulary distinguishes necessary-efficient, necessary-expensive, avoidable, optional/conditional, proposed-not-executed, failed/reverted, missed, and unresolved work. This avoids collapsing “correct but costly” and “unnecessary” into one red label.

The release contains eight stratified scored trajectories—two each from code, writing, internal review, and external peer review—to establish that the full evaluation path runs. It intentionally does not claim a complete 50-task leaderboard.

## 6. Living and growing

A living case is not admitted as a prompt-response pair. A contribution contains Markdown context plus its own disposable repository or LaTeX package and reference solution. Preflight and AI curation check sufficiency, observability, provenance, permission, duplication, pairability, and executability. The case must then pass workspace admission, produce a real trajectory, receive blind action consensus, and enter the canonical scorer.

Successful admission creates a new track version. It does not mutate old cases or backfill new judge behavior into historical scores. `cli-slug-helper` is the first post-bootstrap case to complete this path in the repository.


### Calibration execution and evidence boundary

The eight public calibration trajectories use a **Codex read-only proposal plus allowed-path host executor**. Codex inspects the visible workspace and proposes a patch; the benchmark host applies only authorized edits, then records the diff, checks, and normalized visible trajectory. This is a real workspace execution path, but it is not described as a native Codex self-edit adapter run.

The public release includes the blinded packets, both independent evaluator outputs, and the third adjudication. Its ROI is a deterministic **silver diagnostic**: linked event durations are observed, while problem probability, a 0.1-minute machine-time prior for unmeasured actions, reference origin, and a fallback cheaper substitute are explicit imputations in `evaluation-method.json` and `results.json`. These values are useful for regression comparison, not claims about observed human labor.

## 7. What ships

- 50 independently executable workspace tasks across 25 families;
- 50/50 package admission covering baseline, reference, scope, visible-oracle separation, and checked known-wrong alternatives;
- a normalized cross-Agent trajectory contract;
- Codex, Claude Code, OpenClaw, and custom-command adapters;
- an 8-task scored calibration slice;
- a portable living contribution contract and one admitted example;
- JSON schemas, static HTML reports, offline smoke, wheel resources, and cross-platform CI;
- the older 34-task/544-response collection as a clearly separated static auxiliary track.

## 8. Evidence boundaries

The current references are AI-consensus silver. The release does not claim human gold, real-user satisfaction, or a complete model ranking. Time linked to a recorded event can enter action cost; unattributed wall time remains trajectory-level rather than being invented as a per-action number. External peer review does not receive interaction-burden scores.

## 9. Roadmap

The next valuable evidence is not another internally authored hundred prompts. It is several externally contributed, permissioned workspace failures; replicated baseline/intervention runs; and later, simulated or real interaction tracks with accurately named burden metrics. New frontier-model failure modes should arrive as new immutable tracks while old regressions remain reproducible.
