from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DEFAULT_SMOKE_SOURCE = REPOSITORY_ROOT / "data" / "runs" / "scoring-smoke-v2"
DEFAULT_TRACKS_ROOT = REPOSITORY_ROOT / "tracks"
DEFAULT_FIXTURE_CATALOG = REPOSITORY_ROOT / "living" / "fixture_catalog_v2.json"

