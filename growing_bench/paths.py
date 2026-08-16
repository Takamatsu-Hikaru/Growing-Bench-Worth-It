from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_ROOT.parent
RESOURCE_ROOT = PACKAGE_ROOT / "resources"
REPOSITORY_ROOT = SOURCE_ROOT if (SOURCE_ROOT / "data").is_dir() and (SOURCE_ROOT / "fixtures").is_dir() else RESOURCE_ROOT
DEFAULT_SMOKE_SOURCE = REPOSITORY_ROOT / "data" / "runs" / "scoring-smoke-v2"
DEFAULT_TRACKS_ROOT = REPOSITORY_ROOT / "tracks"
DEFAULT_FIXTURE_CATALOG = REPOSITORY_ROOT / "living" / "fixture_catalog_v2.json"
