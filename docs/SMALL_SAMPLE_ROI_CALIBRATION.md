# Small-sample ROI calibration

This calibration uses real artifact outcomes and measured trajectory wall time.
It does not invent per-action timestamps: the current separate-task export gives
an exact total duration but not an exact duration for every action. Per-action
value therefore uses the manually frozen necessity, problem/success probability
where available, impact, feasibility, opportunity cost, cheaper substitute,
status, and observed result. Wall time remains a trajectory-level cost until the
runner records event timestamps directly.

| Context | Outcome | Wall time | Core actions | Observable burden | ROI conclusion |
|---|---|---:|---:|---:|---|
| Code | baseline 0/2; final 2/2 | 6.91 min | 6 | 3/4 | Positive task value, poor execution efficiency |
| Writing | LaTeX compiled; two intended files changed | 2.55 min | 6 | 1/4 | Positive; one small avoidable build detour |
| Internal review | revise then proceed; no new experiment | 1.19 min | 6 | 0.5/4 | Strong positive decision value |
| External peer review | conditional reject/resubmit | 1.46 min | 8 | N/A | Useful findings, mixed proportionality |

## Code

The implementation, strengthened failure test, and completed test run have high
realized value. The Node 22 assessment has limited value because execution was on
Node 24 and the result is only a static API-compatibility judgment.

The recovery action has negative marginal ROI despite enabling completion: ten
visible failed or reverted patch attempts preceded the bounded fallback. A
cheaper substitute was available after the first confirmed patch-tool failure.
This is not labeled a defensive action; it is avoidable execution overhead with
high opportunity cost and user burden.

## Writing

The evidence review and two section edits have high realized value, and the
declared pdflatex check correctly changes the completion decision. The generic
bibliography-aware build has negative value: it was not required, ended in a
nonblocking BibTeX failure, created misleading generated artifacts, and had the
direct pdflatex command as a cheaper substitute. The final artifact inspection
adds bounded assurance but is lower value than the declared compile check.

## Internal review

The review correctly supports the narrow descriptive result, identifies one
mandatory claim-scope revision, and avoids demanding seeds, confidence intervals,
mechanism work, novelty proof, or broader experiments. The nonblocking prose
bundle is proposed rather than credited as completed work. Separating that edit
from the decision not to require extra experiments prevents optional suggestions
from being scored as work the reviewer forced the author to do.

## External peer review

The future-extrapolation and missing-baseline findings have high decision value.
The method-information finding is mixed: task inputs/labels, correctness rule,
and evaluated-system description are needed to interpret 77.9%, while training
contamination checks, protocol-version detail, and artifact publication depend on
the retained claim and venue contract. Treating the whole bundle as a blocker
raises its opportunity cost.

The full-paper-structure blocker is also mixed because the prompt supplies no
venue or acceptance standard. The review makes its assumption explicit, which is
better than silently universalizing it, but reject/resubmit remains conditional
on that assumption. Optional experiments are correctly kept conditional on
broader claims. External peer review has no user-experience score.

## Metric boundary

A single scalar is not frozen from these four runs yet. Doing so would require
fabricating per-action actual minutes or silently substituting estimates. The
next local runner revision must record event timestamps; then the existing
action-value scorer can combine expected benefit, realized result, feasibility,
measured time, opportunity cost, cheaper substitutes, and applicable user burden.
The small-sample gate is nevertheless meaningful now: it identifies exactly
which selected actions are high value, avoidable, failed, proposed, or dependent
on an unstated assumption before any full run is allowed.
