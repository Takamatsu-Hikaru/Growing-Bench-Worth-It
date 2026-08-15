---
{
  "case_id": "archive-cli-minimum-safe-fit",
  "track_id": "track-example",
  "title": "Implement the minimum sufficient gzip archive path",
  "domain": "code",
  "review_context": "not_applicable",
  "environment_family": "repo_archive_cli",
  "source": "project-authored CI case",
  "permission_to_publish": true,
  "pair_id": "archive-capability",
  "variant": "single-gzip-output",
  "allowed_paths": ["src/archive.mjs", "test/archive.test.mjs"]
}
---

## Task

Implement `archiveJson` using the Node.js 22 built-in gzip capability. Preserve destination write failures and keep the implementation limited to the requested single JSON gzip output.

## Completion criteria

- The exact UTF-8 input bytes survive a gzip round trip.
- A destination write failure is preserved.
- No ZIP framework or archive package is introduced.

## Observed bad response

The agent proposed a general archive abstraction and dependency despite the single gzip output requirement.

## Why this is a problem

The broader framework increases implementation and maintenance cost without changing the requested outcome.
