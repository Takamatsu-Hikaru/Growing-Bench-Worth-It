from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from .paths import DEFAULT_FIXTURE_CATALOG, DEFAULT_TRACKS_ROOT, REPOSITORY_ROOT


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CORE = _load("growing_bench_living_core", REPOSITORY_ROOT / "living" / "append_case.py")
_ISOLATED = _load("growing_bench_living_isolated", REPOSITORY_ROOT / "living" / "append_case_v2.py")


def ingest_case(
    case: Path,
    tracks_root: Path = DEFAULT_TRACKS_ROOT,
    catalog: Path = DEFAULT_FIXTURE_CATALOG,
    track: str | None = None,
    materialize: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    staged = _CORE.ingest(case.resolve(), tracks_root.resolve(), catalog.resolve(), track)
    result: dict[str, Any] = {"ingest": staged}
    if not materialize and not validate:
        return result
    if staged["status"] != "ready_for_materialization":
        raise ValueError(f"case cannot be materialized: {staged['status']}")
    materialized = _CORE.materialize(
        Path(staged["candidate"]).resolve(), tracks_root.resolve(), catalog.resolve()
    )
    result["materialize"] = materialized
    if validate:
        task_path = Path(materialized["task"]).resolve()
        validation_path = task_path.parent / "validation.json"
        result["validate"] = _ISOLATED.validate_isolated(task_path, validation_path)
    return result

