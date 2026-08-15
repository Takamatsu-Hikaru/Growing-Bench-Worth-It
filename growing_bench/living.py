from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_TRACKS_ROOT
from .pipeline import ingest


def ingest_case(
    case: Path,
    tracks_root: Path = DEFAULT_TRACKS_ROOT,
    catalog: Path = DEFAULT_FIXTURE_CATALOG,
    track: str | None = None,
    materialize: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    """Compatibility name for the standalone canonical ingestion pipeline."""

    return ingest(case, tracks_root, catalog, track, materialize, validate)
