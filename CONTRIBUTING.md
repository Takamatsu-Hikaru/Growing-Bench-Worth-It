# Contributing

The most valuable contribution is a concrete interaction where an Agent wasted effort, expanded scope, missed a high-value action, or handled a necessary concern badly.

## Start a case

```bash
python -m growing_bench init-case my-case
python -m growing_bench ingest my-case.md --check
```

The check is read-only. Before opening a pull request, make the goal and completion criteria observable, add a runnable repository or LaTeX fixture when the task changes artifacts, state provenance and public-release permission, and describe a plausible opposite variant.

Then validate the real baseline:

```bash
python -m growing_bench ingest my-case.md --materialize --validate
python -m growing_bench smoke --output runs/contributor-smoke
python -m unittest tests.test_public_cli tests.test_agent_adapters tests.test_public_release tests.test_product_experience
```

New cases enter a new track as `silver_pending`. Existing tracks and scores remain unchanged. Semantic duplicates should declare a `supersedes` relationship.

## Submit an Agent adapter

Adapters must preserve the common artifacts in `docs/AGENT_ADAPTERS.md`. They may translate vendor events, but fixture isolation, expected-baseline validation, allowed-path enforcement, and scoring stay in the shared harness.

Add offline tests for success, timeout, missing CLI, and out-of-scope modification behavior.

## Naming evidence accurately

Machine consensus is `silver_reference`, `consensus_reference`, or `ai_adjudicated_reference`, never human gold. Disagreements remain unresolved. Simulated interaction burden is not real user satisfaction.
