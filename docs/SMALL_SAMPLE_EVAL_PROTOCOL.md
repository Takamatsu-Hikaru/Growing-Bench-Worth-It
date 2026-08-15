# Small-sample evaluation gate

Workspace tasks are not allowed to scale directly from a successful run.

For one task in each context, first retain the task prompt, editable workspace,
before/after checks, changed files, diff, wall time, and visible trajectory. Then
manually inspect the following before adding more tasks:

1. The final artifact must satisfy executable or compile-based checks. A fluent
   answer is not task success.
2. Actions are independently choosable units of work, not sentences, tool calls,
   library calls, or every retry. Repeated retries may be grouped, but their count
   and elapsed cost must remain visible.
3. Status must distinguish completed, failed, reverted, refused, proposed, and
   completed-with-limit. A failed attempt cannot inherit the final result.
4. ROI inputs are marked per action: requested, required, outcome impact,
   decision impact, feasibility, opportunity cost, cheaper substitute, observed
   result, actual time where measurable, and observable user burden for direct
   user-facing tasks.
5. Do not call ordinary implementation or debugging `defensive`. That label is
   reserved for a concrete guard, refusal, audit, validation, permission check,
   or risk-control action. Even then, the necessity conditions are evaluated
   separately.
6. External peer review excludes user-experience scoring. Writing, code, and
   internal review retain observable burden and direct participant feedback.
7. Compare the automatic extraction to the manual action list. Correct the
   extractor or rubric until the small sample is credible; only then run the
   remaining tasks.

The first calibrated code sample is
`runs/workspace-code-gzip-sol-smoke-v3/manual_action_review.json`. It has seven
meaningful actions. Ten visible patch failures are preserved as the cost of one
environment-recovery action rather than inflated into ten independent decisions.
