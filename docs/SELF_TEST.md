# Self-test workflow

`growing-bench self-test` is the product entry point for comparing an Agent with and without a skill, prompt, plugin, or harness intervention.

## Pipeline

```text
fixed task suite
  -> fresh baseline workspace
  -> fresh intervention workspace
  -> visible trajectories and verified outcomes
  -> condition-blind LLM action judgment
  -> canonical deterministic scorer
  -> paired results.json and report.html
  -> optional append into a portable living case
```

Baseline and intervention use the same Agent, model settings, tasks, completion checks, judge prompt, isolation request, and scorer. The judge packet does not contain condition identity.

`--isolation copy` uses the fresh fixture copy as the portable boundary. `--isolation agent-native` additionally requires a supported native sandbox and currently accepts the Codex adapter. Other adapters fail before execution instead of silently claiming a sandbox they do not provide.

## Suites

`quick` contains one task from each context. `balanced` contains four matched decision boundaries. Use `--context` to select code, writing, internal review, or external peer review. Repeat `--task path/to/task.json` to run an explicit local set.

## Judge contract

The judge splits the visible trajectory into atomic actions and assigns `necessary`, `optional`, `avoidable`, or `unresolved`. Missing required work is recorded separately as `missed`.

`necessary` passes only when:

1. `requirement_id` maps to an explicit completion criterion.
2. `omission_consequence` states the concrete failure or evidenced material risk.
3. `atomic` is true.

A missing gate changes the label to `unresolved`. An avoidable action requires both a reason and a cheaper substitute.

`--strict` runs evaluator A and evaluator B independently. It stores both raw judgments, extraction agreement, label agreement, confidence, and disagreement categories. A third condition-blind adjudicator runs when the judgments differ and is instructed to preserve genuine uncertainty as `unresolved`.

`growing-bench calibrate-judge` runs the current prompt over 20 frozen actions across 10 decision boundaries.

## Cost data

Each action time records a source and method:

| Source | Method |
|---|---|
| `observed` | visible event duration |
| `estimated` | LLM estimate |
| `imputed` | fixed default action prior |

The report keeps necessity and cost separate. It also shows whole-run elapsed time, tokens when available, touched files, checks, tool events, and trajectory completeness. ROI appears as an experimental secondary diagnostic.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | all requested runs and judgments completed |
| 1 | an Agent run failed or a partial self-test was produced |
| 2 | command input or local setup error |
| 3 | the evaluator or judge calibration failed |

`--allow-partial` keeps usable results and permits success only when at least one score exists.

## Output

```text
run/
  run-card.json
  intervention.md
  results.json
  report.html
  runs/<task>--baseline/
  runs/<task>--intervention/
  judgments/<task>--baseline/
    packet.json
    evaluator-a.json
    evaluator-b.json       # strict mode
    adjudicator-c.json     # when needed
    consensus.json
    agreement.json
    bundle.json
```

## Append

`growing-bench append` selects a useful failure from a self-test and creates a portable case draft. The draft contains the fixture, minimal successful reference change, selected trajectory and judgment, both baseline/intervention evidence folders, a comparison summary, redaction results, and ingest preflight.
