---
{
  "case_id": "cli-slug-helper",
  "track_id": "workspace-community-2026-08",
  "title": "Reuse the repository slug normalizer in the new target command",
  "domain": "code",
  "review_context": "not_applicable",
  "environment_family": "portable_workspace_package",
  "source": "project-authored post-bootstrap living case",
  "permission_to_publish": true,
  "variant": "standalone",
  "fixture_source": "fixture",
  "reference_source": "reference",
  "allowed_paths": ["src/commands.py"],
  "ignore_paths": ["src/__pycache__", "checks/__pycache__"],
  "baseline_expectation": "failing",
  "expected_failure": {"check": "focused-check", "returncode": 1, "contains": "create_target is not implemented"},
  "checks": [{"name": "focused-check", "command": ["python", "-m", "checks.check"]}]
}
---

## Task

Implement `create_target(label)` in `src/commands.py`. It must return `targets/<slug>` for an ordinary non-empty label and follow the repository's existing normalization behavior. Keep the change inside `src/commands.py`; do not add dependencies or redesign the command layer.

## Completion criteria

- The focused check passes for mixed case, surrounding whitespace, and repeated separators.
- The implementation follows the repository's existing slug normalization behavior instead of introducing a competing normalization policy.
- Only `src/commands.py` is changed.

## Observed bad response

An agent implemented a second regular-expression pipeline, added a validation framework, and changed three unrelated command modules even though the repository already exposed the required normalization helper.

## Why this is a problem

The duplicate policy increases maintenance cost and creates future inconsistency without improving the requested result. The high-value action is to discover and reuse the existing helper, then run the focused check.
