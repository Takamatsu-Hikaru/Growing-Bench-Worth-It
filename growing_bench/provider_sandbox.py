"""Trusted transport for provider tools. There is deliberately no host fallback.

Each operation gets a fresh, bounded Docker container. Only regular workspace
files cross the JSON bridge; no host workspace, credentials or Docker socket is
mounted. Processes and temporary state die at the end of every operation.
"""
from __future__ import annotations

import base64
import json
import hashlib
import os
import shutil
import stat
import subprocess
import uuid
from pathlib import Path, PurePosixPath

POLICY = "provider-docker-v1"
DEFAULT_IMAGE = "sha256:ffffba3688e3b63fb7dbf059ca7a49c7aabfe21648118d6336057c63b575b4fb"
BUILD_TAG = "growing-bench-agent:0.2"
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_FILES = 10000
BRIDGE = Path(__file__).resolve().parent / "container_tool.py"
DOCKERFILE = Path(__file__).resolve().parent / "resources" / "agent.Dockerfile"
CONFIG = Path.home() / ".growing-bench" / "adapter.json"


def provider_command(template):
    if not template:
        return False
    try:
        parts = json.loads(template)
    except (json.JSONDecodeError, TypeError):
        return False
    normalized = [str(part).replace("\\", "/") for part in parts]
    return "growing_bench.openai_compatible" in normalized


def image_id():
    configured = os.environ.get("GROWING_BENCH_IMAGE")
    if configured:
        return configured
    if CONFIG.is_file():
        value = json.loads(CONFIG.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("image_id"), str):
            return value["image_id"]
    return DEFAULT_IMAGE


def profile():
    return {"requested_mode": POLICY, "enforced_container_or_vm": True,
            "image": image_id(),
            "network_access": False, "docker_network_mode": "none", "user": "1000:1000",
            "read_only_root": True, "host_workspace_mount": False,
            "cpus": 2, "memory_bytes": 2147483648, "pids_limit": 128,
            "gpu_access": False, "lifetime": "one tool/check operation",
            "persisted_state": "validated regular workspace files only"}


def _relative(name):
    if not isinstance(name, str):
        raise ValueError("Invalid workspace artifact path")
    path = PurePosixPath(name)
    if (not name or name == "." or "\\" in name or ":" in name
            or "\x00" in name or path.is_absolute() or str(path) != name
            or any(p.casefold() in {"..", ".git"} or p.rstrip(" .") != p
                   or any(ord(c) < 32 or c in '<>"|?*' for c in p)
                   or p.split(".")[0].casefold() in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
                   for p in path.parts)):
        raise ValueError("Invalid workspace artifact path")
    return path


def pack(root):
    root = Path(root).resolve()
    files, total = {}, 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Workspace directory symlinks cannot cross the container boundary")
            if name in {".git", "__pycache__"}:
                dirs.remove(name)
        for name in names:
            path = Path(directory) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Only regular, unlinked workspace files may be imported")
            relative = path.relative_to(root).as_posix()
            _relative(relative)
            total += info.st_size
            if info.st_size > MAX_FILE or total > MAX_BYTES or len(files) >= MAX_FILES:
                raise ValueError("Workspace exceeds artifact limits")
            files[relative] = base64.b64encode(path.read_bytes()).decode("ascii")
    return files


def restore(root, snapshot):
    # Validate the entire response before changing any host file. Never extract
    # a model-produced tar archive or recreate symlinks, devices or hardlinks.
    if snapshot.get("unsupported_symlinks") or snapshot.get("unsupported_files"):
        raise ValueError("Container produced unsupported links or special files")
    files = snapshot["files"]
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("Invalid workspace snapshot")
    decoded, total = {}, 0
    for name, encoded in files.items():
        path = _relative(name)
        data = base64.b64decode(encoded, validate=True)
        total += len(data)
        if len(data) > MAX_FILE or total > MAX_BYTES:
            raise ValueError("Workspace export exceeds artifact limits")
        decoded[path] = data
    for path in decoded:
        if any(parent in decoded for parent in path.parents):
            raise ValueError("Conflicting workspace artifact paths")
    root = Path(root).resolve()
    for path in decoded:
        if not root.joinpath(*path.parts).resolve().is_relative_to(root):
            raise ValueError("Workspace artifact resolves outside the task directory")
    existing = pack(root)  # Also rejects pre-existing host symlinks/hardlinks.
    for name in existing:
        if PurePosixPath(name) not in decoded:
            (root / name).unlink()
    # Prune empty directories so file-to-directory and directory-to-file edits work.
    for directory, dirs, _ in os.walk(root, topdown=False):
        for name in dirs:
            path = Path(directory) / name
            if name != ".git" and not any(path.iterdir()):
                path.rmdir()
    for path, data in decoded.items():
        destination = root.joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def _scope(root):
    return os.environ.get("GROWING_BENCH_WORKSPACE_SCOPE") or hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()


def preflight():
    if shutil.which("docker") is None:
        raise RuntimeError("Provider execution requires Docker; host execution is disabled")
    image = image_id()
    if not image.startswith("sha256:") or len(image) != 71:
        raise RuntimeError("Use a pinned Docker image ID, not a mutable tag")
    if not BRIDGE.is_file():
        raise RuntimeError("Container tool bridge is missing")
    value = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=20)
    if value.returncode:
        raise RuntimeError(
            "Prepared Docker image is unavailable. Run 'growing-bench setup-adapter' first."
        )
    config = json.loads(value.stdout)[0]["Config"]
    if config.get("Volumes"):
        raise RuntimeError("Task image must not declare implicit host-backed volumes")
    tex = os.environ.get("GROWING_BENCH_TEX_ROOT")
    tex_root = Path(tex).resolve() if tex else None
    if tex_root and not (tex_root / "bin" / "x86_64-linux" / "pdflatex").is_file():
        raise RuntimeError("GROWING_BENCH_TEX_ROOT does not contain TinyTeX")
    return image, tex_root


def build_image() -> dict:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is not installed or not on PATH")
    if not DOCKERFILE.is_file():
        raise RuntimeError("Packaged Agent Dockerfile is missing")
    completed = subprocess.run(
        ["docker", "build", "-t", BUILD_TAG, "-f", str(DOCKERFILE), str(DOCKERFILE.parent)],
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Docker image build failed with exit code {completed.returncode}")
    inspected = subprocess.run(
        ["docker", "image", "inspect", BUILD_TAG, "--format", "{{.Id}}"],
        capture_output=True, text=True, timeout=20, check=True,
    )
    resolved = inspected.stdout.strip()
    if not resolved.startswith("sha256:") or len(resolved) != 71:
        raise RuntimeError("Docker did not return an immutable image ID")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        json.dumps({"schema_version": "growing-bench-adapter-runtime-1.0", "image_id": resolved}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"status": "completed", "image": BUILD_TAG, "image_id": resolved}


def cleanup_workspace(root):
    """Reap only this workspace's containers after a controller timeout."""
    label = "growing-bench.workspace=" + _scope(root)
    found = subprocess.run(["docker", "ps", "-aq", "--filter", "label=" + label],
                           capture_output=True, text=True, timeout=20, check=True)
    for container in found.stdout.split():
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=20, check=True)


def execute(root, task, name, arguments):
    image, tex = preflight()
    container = "growing-provider-" + uuid.uuid4().hex
    request = {"tool": name, "arguments": arguments, "checks": task.get("checks", []),
               "files": pack(root)}
    command = ["docker", "run", "--rm", "-i", "--name", container,
               "--label", "growing-bench.policy=" + POLICY,
               "--label", "growing-bench.workspace=" + _scope(root),
               "--network", "none", "--read-only", "--user", "1000:1000",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--cpus", "2", "--memory", "2g", "--memory-swap", "2g",
               "--pids-limit", "128", "--ulimit", "nofile=256:256",
               "--ulimit", "fsize=67108864:67108864", "--init", "--ipc", "none",
               "--log-driver", "none", "--workdir", "/workspace",
               "--tmpfs", "/workspace:rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=700",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=700",
               "--mount", f"type=bind,src={BRIDGE},dst=/bridge/tool.py,readonly"]
    if tex is not None:
        command.extend(["--mount", f"type=bind,src={tex},dst=/opt/tinytex,readonly"])
    command.extend(["--entrypoint", "python", image, "-I", "-B", "/bridge/tool.py"])
    try:
        completed = subprocess.run(command, input=json.dumps(request), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=210)
        if completed.returncode:
            raise RuntimeError(f"Isolated tool failed ({completed.returncode}): {completed.stderr[:2000]}")
        response = json.loads(completed.stdout)
        restore(root, response["snapshot"])
        return {**response["result"], "execution_boundary": POLICY}
    finally:
        # Also terminates descendants when the client times out or the bridge dies.
        cleanup = subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=20)
        if cleanup.returncode and b"No such container" not in cleanup.stderr:
            raise RuntimeError("Container cleanup failed; stop dispatch before starting another task")
