# Provisional ROI results

The four frozen small samples were scored with the ex-post diagnostic in
`provisional_roi.py`. Values are useful within a trajectory; totals are not a
leaderboard because tasks have different numbers of independently useful actions.

| Task | Actual wall min | Core actions | Trajectory value | Mean/action | Nonpositive actions |
|---|---:|---:|---:|---:|---:|
| Code gzip | 6.9115 | 6 | 9.9642 | 1.6607 | 1 |
| LaTeX writing | 2.5545 | 6 | 14.9547 | 2.4924 | 1 |
| Internal review | 1.1930 | 6 | 17.0455 | 2.8409 | 1 |
| External peer review | 1.4572 | 8 | 20.1779 | 2.5222 | 0 |

The diagnostic correctly surfaces the intended low-value cases:

- Code A2, repeated environment recovery: -0.25 before trajectory time.
- Writing A4, unnecessary generic bibliography build: -0.75.
- Internal review A5, proposed nonblocking prose cleanup: -0.125 because it was
  not executed and still carries a small opportunity cost.

External review has no negative action, but its questionable full-paper-structure
blocker is nearly neutral at 0.15, the nonblocking revision bundle is 0.75, and
the over-bundled method-transparency blocker is 1.375. The unsupported future
claim and real baseline inconsistency each retain high value. This is the desired
behavior: skepticism is not punished by label, but a blocker with weak necessity,
an unstated assumption, high opportunity cost, or a cheaper scoped alternative
loses ROI.

The JSON result is `runs/workspace-small-sample-roi-v1.json`. A future
timestamped runner can replace the single trajectory wall-time cost with exact
per-action time. Until then, these values are calibration evidence, not published
benchmark scores.
