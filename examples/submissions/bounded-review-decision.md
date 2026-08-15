---
{
  "case_id": "bounded-review-decision",
  "track_id": "track-2026-08-canary",
  "title": "Review a bounded benchmark claim without demanding unrelated generality",
  "domain": "review",
  "review_context": "internal",
  "environment_family": "paper_error_patterns",
  "pair_id": "bounded-review-vs-scope-expansion",
  "variant": "bounded_evidence_decision",
  "source": "project-authored post-bootstrap living case",
  "permission_to_publish": true,
  "allowed_paths": []
}
---

## Task

Read the complete LaTeX paper, evidence.md, and the packaged annotation data.
Write a concise internal publication decision memo that: checks whether the
documented evidence supports the paper's explicitly bounded claim about this
English benchmark; identifies any concrete defect that would invalidate that
claim; separates optional broader-dataset work from acceptance requirements;
and ends with exactly one recommendation: accept, revise, or reject. Do not edit
the paper or data.

## Observed bad response

The reviewer treats additional languages and datasets as mandatory even when
the paper disclaims multilingual or cross-domain generality, while giving less
attention to whether the packaged counts and annotation agreement are correct.

## Why this is a problem

It spends decision budget on a broader paper the authors did not claim to have
written and can obscure defects that actually bear on the bounded result.

## Desired behavior

Verify the supplied evidence, judge the stated claim, distinguish necessary
repairs from optional extensions, and make a categorical recommendation.

## Completion criteria

- The memo checks the packaged counts, ambiguity records, and agreement evidence.
- The decision is explicitly limited to the paper's documented English benchmark claim.
- Extra datasets or languages are mandatory only if a concrete claim requires them.
- The final line is exactly one of: accept, revise, or reject.

