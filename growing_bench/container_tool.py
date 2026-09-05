"""Fixed tool executor mounted read-only into disposable Agent containers."""
from __future__ import annotations

import base64
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path("/workspace")
PROGRAMS = {"python", "python3", "node", "git", "pdflatex", "tectonic", "latexmk"}


def snapshot():
    files, links, special, total = {}, [], [], 0
    for directory, dirs, names in os.walk(ROOT, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if path.is_symlink():
                links.append(path.relative_to(ROOT).as_posix())
                dirs.remove(name)
            elif name in {".git", "__pycache__", "node_modules"}:
                dirs.remove(name)
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                links.append(relative)
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                special.append(relative)
                continue
            size = info.st_size
            total += size
            if size > 32 * 1024 * 1024 or total > 64 * 1024 * 1024 or len(files) >= 10000:
                raise ValueError("Workspace export exceeds the 64 MiB task-artifact limit")
            files[relative] = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "files": files,
        "unsupported_symlinks": links,
        "unsupported_files": special,
        "total_bytes": total,
    }


def workspace_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or ".git" in path.relative_to(ROOT).parts:
        raise ValueError("Path must remain inside the task workspace, outside .git.")
    return path


def execute(request):
    name, args = request["tool"], request["arguments"]
    if name in {"run_check", "run_command"}:
        if name == "run_check":
            check = next(row for row in request["checks"] if row["name"] == args["name"])
            argv = check["command"]
            if argv[:2] == ["cmd", "/c"]:
                argv = argv[2:]
            timeout = min(float(check.get("timeout_seconds", 90)), 180)
        else:
            argv, timeout = args["argv"], 90
            if not argv or argv[0] not in PROGRAMS:
                raise ValueError("Available programs: " + ", ".join(sorted(PROGRAMS)))
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                argv,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            stdout.seek(0)
            stderr.seek(0)
            out, err = stdout.read(1000001), stderr.read(1000001)
        return {
            "returncode": None if timed_out else process.returncode,
            "stdout": out[:1000000].decode("utf-8", errors="replace"),
            "stderr": err[:1000000].decode("utf-8", errors="replace"),
            "timed_out": timed_out,
            "output_truncated": len(out) > 1000000 or len(err) > 1000000,
        }
    path = workspace_path(args["path"])
    if name == "list_files":
        return {
            "files": [
                item.relative_to(ROOT).as_posix()
                for item in sorted(path.rglob("*"))
                if item.is_file()
                and not any(part in {".git", "__pycache__", "node_modules"} for part in item.parts)
            ]
        }
    if name == "read_file":
        return {"path": args["path"], "content": path.read_text(encoding="utf-8")}
    if name == "write_file":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8", newline="\n")
        return {"written": args["path"]}
    if name == "replace_text":
        original = path.read_text(encoding="utf-8")
        if original.count(args["old"]) != 1:
            raise ValueError("old text must match exactly once")
        path.write_text(original.replace(args["old"], args["new"], 1), encoding="utf-8", newline="\n")
        return {"updated": args["path"]}
    raise ValueError("Unknown tool")


def main() -> int:
    os.environ.clear()
    os.environ.update(
        PATH="/opt/tinytex/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin",
        HOME="/tmp",
        LANG="C.UTF-8",
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR="/tmp",
        TEXMFVAR="/tmp/texmf-var",
        TEXMFCONFIG="/tmp/texmf-config",
    )
    try:
        request = json.load(sys.stdin)
        for name, data in request.pop("files").items():
            path = workspace_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(data, validate=True))
        try:
            result = execute(request)
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        response = {"result": result, "snapshot": snapshot()}
    except Exception as exc:
        print(f"Container bridge failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
