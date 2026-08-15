# Contributing

The most valuable contribution is a concrete AI interaction that wasted effort, expanded scope, missed the real objective, or handled a necessary concern badly.

## Submit a case

Copy a template from `living/examples/` and include:

- the user goal and enough context to reproduce it;
- observable completion criteria;
- a repository or LaTeX fixture when the task changes artifacts;
- the behavior being tested and its plausible opposite failure;
- provenance and explicit permission for public release;
- any model, agent, or date metadata you are comfortable publishing.

Before opening a pull request:

```bash
python -m growing_bench ingest path/to/case.md --materialize --validate
python -m growing_bench smoke --output runs/contributor-smoke
python -m unittest tests.test_public_cli tests.test_agent_adapters
```

New cases enter a new track as `silver_pending`. Existing tracks and scores are immutable. Semantic duplicates should declare a `supersedes` relationship rather than replacing history.

## Submit an adapter

Adapters must preserve the common run artifacts described in `docs/AGENT_ADAPTERS.md`. They may translate a vendor event stream, but must not move baseline checks, allowed-path validation, or benchmark scoring into vendor-specific code.

## Label policy

Machine consensus is called `silver_reference`, `consensus_reference`, or `ai_adjudicated_reference`. Do not call it human gold. Disagreements stay unresolved and are excluded or reported separately. Simulated interaction metrics must not be presented as real user satisfaction.

