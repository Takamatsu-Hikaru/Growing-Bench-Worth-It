from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .paths import DEFAULT_SMOKE_SOURCE
from .reporting import render_report
from .scoring import score_frozen_run


FROZEN_INPUTS = ("preannotation_bundles.jsonl", "annotation_packets.jsonl", "dimension.silver.json")


def run_smoke(output: Path, source: Path = DEFAULT_SMOKE_SOURCE) -> dict[str, Any]:
    source, output = source.resolve(), output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"smoke output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for name in FROZEN_INPUTS:
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(f"frozen smoke input is missing: {path}")
        shutil.copyfile(path, output / name)
    results = score_frozen_run(output)
    report = render_report(output)
    return {
        "status": "completed", "trajectory_count": results["trajectory_count"],
        "portfolio_roi": results["portfolio_roi"], "results": str(output / "results.json"),
        "scores": str(output / "scores.jsonl"), "report": str(report),
        "uses_external_model": False,
    }

