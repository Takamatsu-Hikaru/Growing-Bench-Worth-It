# Public data

This directory is the standalone public data surface.

- `tasks/tasks.jsonl`: 34 canonical tasks.
- `tasks/pairs.json`: 17 matched groups and variants.
- `tasks/provenance.jsonl`: source and license metadata.
- `references/silver_reference.json`: 34 AI-adjudicated reference plans.
- `runs/public-544-v1/results.public.jsonl`: 544 completed model responses.
- `runs/scoring-smoke-v2/`: the three frozen inputs needed by the offline ROI smoke.

AI-adjudicated references are silver references, not human gold. The 544-response file is a public response slice, not a completed final leaderboard: full action-level judging is intentionally not claimed in v0.1.

