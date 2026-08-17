from __future__ import annotations

from pathlib import Path
from typing import Any

from .quality import find_mojibake


NEXT_STEPS = {
    "title": "Add a concrete title to the JSON frontmatter.",
    "domain": "Set domain to code, writing, or review.",
    "review_context": "Set review_context to not_applicable, internal, or external_peer.",
    "source": "Describe where the case came from.",
    "permission_to_publish": "Set permission_to_publish explicitly. False is fine for local use.",
    "fixture_source": "Add a fixture directory beside case.md and name it in fixture_source.",
    "reference_source": "Add the minimal successful change in a reference directory.",
    "allowed_paths": "List the paths the Agent may modify.",
    "section:Task": "Add a ## Task section containing the exact Agent request.",
    "section:Completion criteria": "Add observable bullet points under ## Completion criteria.",
}


def _encoding_issues(case: Path) -> list[dict[str, Any]]:
    root = case.parent.resolve()
    rows = []
    for path in [case, *root.rglob("*")]:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            rows.append({
                "code": "invalid_utf8",
                "path": str(path.relative_to(root)),
                "message": "The file is not valid UTF-8.",
                "next_step": "Convert this text file to UTF-8 and run ingest --check again.",
                "severity": "warning",
                "local_use_allowed": True,
            })
            continue
        if find_mojibake(text):
            rows.append({
                "code": "encoding_damage",
                "path": str(path.relative_to(root)),
                "message": "Replacement characters such as � or �� were found.",
                "next_step": "Repair the damaged characters before sharing the case.",
                "severity": "warning",
                "local_use_allowed": True,
            })
    return rows


def enrich_preflight(result: dict[str, Any], case: Path) -> dict[str, Any]:
    value = dict(result)
    issues = []
    for missing in value.get("missing", []):
        issues.append({
            "code": "missing_field",
            "path": "case.md",
            "message": f"Missing {missing}.",
            "next_step": NEXT_STEPS.get(missing, f"Add or correct {missing} and run ingest --check again."),
            "severity": "error",
            "local_use_allowed": False,
        })
    for duplicate in value.get("duplicates", []):
        issues.append({
            "code": "possible_duplicate",
            "path": str(duplicate),
            "message": "The normalized task text matches an existing staged case.",
            "next_step": "Add supersedes metadata or explain the distinct decision boundary.",
            "severity": "warning",
            "local_use_allowed": True,
        })
    checks = value.get("checks", {})
    if checks.get("publication_permission") is False or checks.get("publication_permission_explicit") is False:
        issues.append({
            "code": "publication_permission",
            "path": "case.md",
            "message": "The case can stay local but cannot enter a public track yet.",
            "next_step": "Set permission_to_publish to true only after the owner approves publication.",
            "severity": "warning",
            "local_use_allowed": True,
        })
    issues.extend(_encoding_issues(case.resolve()))
    value["issues"] = issues
    value["local_use_allowed"] = not any(not row["local_use_allowed"] for row in issues)
    value["public_admission_ready"] = value.get("status") in {"ready_for_ai_curation", "ready_for_materialization"} and not any(row["severity"] == "error" for row in issues)
    return value
