from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Any

from .agents import BUILTIN_AGENTS, probe_agent
from .paths import DEFAULT_SMOKE_SOURCE


def _tool(name: str, version_args: list[str]) -> dict[str, Any]:
    executable = shutil.which(name)
    if executable is None:
        return {"available": False, "version": None}
    try:
        value = subprocess.run([executable, *version_args], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=10, check=False)
        version = (value.stdout or value.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        version = "unknown"
    return {"available": True, "version": version}


def doctor() -> dict[str, Any]:
    agents = {name: probe_agent(name) for name in BUILTIN_AGENTS}
    tools = {"node": _tool("node", ["--version"]), "pdflatex": _tool("pdflatex", ["--version"]), "docker": _tool("docker", ["--version"]), "git": _tool("git", ["--version"])}
    frozen = ("preannotation_bundles.jsonl", "annotation_packets.jsonl", "dimension.silver.json")
    smoke_ready = all((DEFAULT_SMOKE_SOURCE / name).is_file() for name in frozen)
    return {
        "schema_version": "growing-bench-doctor-1.1",
        "python": {"available": sys.version_info >= (3, 10), "version": platform.python_version()},
        "platform": platform.platform(), "agents": agents, "tools": tools,
        "offline_smoke_ready": smoke_ready,
        "offline_smoke_note": "ready" if smoke_ready else "clone the repository to access benchmark data and fixtures",
        "live_agent_count": sum(1 for name, row in agents.items() if name != "command" and row["available"]),
    }
