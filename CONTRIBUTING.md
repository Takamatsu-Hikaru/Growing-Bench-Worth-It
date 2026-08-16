# Contributing

The most valuable contribution is a concrete Agent trajectory where work was avoidable, scope expanded, a high-value action was missed, or a necessary concern was handled badly.

## Contribute a portable case

```bash
growing-bench init-case my-case
```

This creates:

```text
my-case/
  case.md       # task, criteria, provenance, permission, observed failure
  fixture/      # initial disposable repository or LaTeX package
  reference/    # smallest solution that proves the task is executable
```

Use fake credentials and stub services. Do not submit production secrets, private conversations without permission, or a fixture that depends on an account you control.

Run the read-only preflight:

```bash
growing-bench ingest my-case/case.md --check
```

It reports information gaps, observable criteria, publication permission, duplicate risk, pairability, and fixture/reference readiness. A prompt and response without an executable workspace may remain auxiliary QA data, but it cannot enter the workspace benchmark.

Portable materialization requires a separate AI-curator decision covering all seven admission questions:

```bash
growing-bench ingest my-case/case.md \
  --materialize --validate --curation my-case/curation.ai.json
```

The repository's complete example is `living/contributions/cli-slug-helper/`. New cases enter a new immutable track. They do not rewrite historical cases or scores; semantic replacements declare `supersedes`.

Before a pull request, run:

```bash
growing-bench smoke --output runs/contributor-smoke
python -m unittest tests.test_public_cli tests.test_agent_adapters tests.test_adapter_golden_events tests.test_workspace_runner_v2
```

## Contribute an Agent adapter

Adapters translate a vendor's command and visible events. Growing Bench retains fixture isolation, baseline validation, completion checks, path scope, diffing, and scoring.

Add a recorded no-network golden stream and tests for parsing, success, timeout, missing CLI, and out-of-scope changes. Credentials and private chain-of-thought must never enter public events.

## Name evidence accurately

Machine consensus is `silver_reference`, `consensus_reference`, or `ai_adjudicated_reference`, never human gold. Unresolved disagreements remain visible. Simulated interaction burden is not real-user satisfaction. An eight-task calibration is not a 50-task leaderboard.
