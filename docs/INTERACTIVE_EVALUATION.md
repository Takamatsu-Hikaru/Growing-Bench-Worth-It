# Interactive evaluation

Growing Bench can evaluate how an Agent updates across a real multi-turn workspace session. The tested Agent keeps one workspace and one conversation session while a controlled user policy introduces corrections, retires earlier concerns, or changes the live decision boundary.

## Run one scenario

```bash
growing-bench interact growing_bench/resources/interactive/code-reuse-helper-present.json \
  --agent codex \
  --output runs/code-reuse-interaction
```

The run directory contains the exact user and Agent messages, normalized tool events, each turn's diff, final workspace diff, checks, elapsed time, and controller state. Scripted user moves are the reproducible default. `--user-mode simulated` lets a configured Agent paraphrase a supplied move, but it may not add facts, goals, or judgments.

## Compare an intervention

```bash
growing-bench self-test examples/interventions/proportional-work.md \
  --mode interactive \
  --suite quick \
  --agent codex \
  --judge codex \
  --strict \
  --output runs/proportional-work-interactive
```

The action evaluator and canonical scorer still measure task success, necessary-action recall, avoidable work, cost, missed value, and trajectory ROI. A separate condition-blind interaction evaluator labels literal visible spans and explicit user signals. Its deterministic summary separates `scenario_pressure`, such as scripted correction turns and a planned takeover, from `observed_agent_burden`, which counts ignored or partially honored signals, stale reintroductions, unnecessary compliance receipts, and unnecessary self-report. A perfect Agent can therefore receive zero observed burden even in a demanding scenario. The evaluator never infers feelings or reports real user satisfaction.

The bundled quick suite has four contexts. The balanced suite has eight real workspace scenarios covering both sides of four decision boundaries: reuse versus local implementation, fixed-set versus sampled writing claims, deterministic versus stochastic review evidence, and irrelevant versus claim-changing extra experiments.

## Scenario contract

Each scenario JSON names a real packaged task and at least two user moves. Every move has a stable `move_id`, a role, a visible message, state topics it activates or retires, and the signals the evaluator must track. A topic is stale only after the controller retires it.

```json
{
  "schema_version": "growing-bench-interactive-scenario-1.0",
  "scenario_id": "interactive--example",
  "base_task_id": "workspace-v0.2--example",
  "user_profile": {"goal": "ship the bounded change"},
  "turns": [
    {
      "move_id": "initial",
      "role": "initial",
      "message": "$TASK_PROMPT",
      "activates": ["workspace_task"],
      "retires": [],
      "targets": ["complete_workspace_task"]
    },
    {
      "move_id": "update",
      "role": "correction",
      "message": "Use the existing compatible helper and keep the change local.",
      "activates": ["reuse_helper"],
      "retires": ["generic_framework"],
      "targets": ["reuse_decision", "scope_update"]
    }
  ]
}
```

## Adapter persistence

Codex uses its native resumable task session. Claude Code uses a persistent session ID. OpenClaw uses explicit transcript replay until its installed CLI exposes an equivalent resumable contract. Arbitrary command adapters receive `workspace`, `prompt_file`, `session_dir`, `session_id`, and `turn_index` placeholders and declare their persistence as adapter-managed. For replay-based adapters, the intervention is an explicit session policy and is included in every turn prompt; native resumable sessions receive it on the first turn and preserve it in session state.

## Grow from an interaction

```bash
growing-bench append runs/proportional-work-interactive \
  --title "Agent kept reintroducing a retired concern" \
  --output my-interactive-case
```

The draft keeps the runnable fixture, controller, exact visible trajectory, both semantic judgments, and a lower-burden comparison workspace. It can enter the existing living-case curation and versioned-track pipeline.
