# Living case pipeline

The public entry point is:

```bash
python -m growing_bench ingest path/to/case.md --materialize --validate
```

A case always enters a new track as staging. Markdown parsing alone never creates a benchmark task or score.

The pipeline checks:

1. task context and observable completion criteria;
2. provenance and explicit publication permission;
3. duplicate and supersedes metadata;
4. positive/negative pair metadata;
5. a supported real repository or LaTeX fixture;
6. the declared passing baseline or exact expected failing baseline.

Successful validation materializes a portable task with `reference_status: silver_pending`. Agent execution, action extraction, AI consensus, ROI scoring, and track admission remain separate gates. New model eras or new failure families use a new `track_id`; old tracks and old scores are not rewritten.

Use `examples/case.md` for a LaTeX task or `examples/code_case.md` for a repository task.

