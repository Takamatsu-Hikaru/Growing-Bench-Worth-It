from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from build_workspace_track import TRACK, code_specs, review_specs, task_id, writing_specs


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def latex(value: str) -> str:
    return value.replace("%", "\\%").replace("_", "\\_")


WRITING_VISIBLE_CHECK = """from pathlib import Path

TARGETS = {targets!r}
try:
    values = [Path(path).read_text(encoding="utf-8").strip() for path in TARGETS]
    assert values and all(len(value) >= 30 for value in values)
    assert all("WORKSPACE TASK INCOMPLETE" not in value for value in values)
except Exception:
    print("WORKSPACE_TASK_INCOMPLETE")
    raise SystemExit(1)
print("format ok")
"""


REVIEW_VISIBLE_CHECK = """import json
from pathlib import Path

try:
    value = json.loads(Path("review.json").read_text(encoding="utf-8"))
    assert set(value) == {"decision", "evidence_ids", "required_actions", "optional_actions", "rationale"}
    assert value["decision"] in {"accept", "revise", "reject"}
    assert all(isinstance(value[name], list) for name in ("evidence_ids", "required_actions", "optional_actions"))
    assert all(isinstance(item, str) and item for name in ("evidence_ids", "required_actions", "optional_actions") for item in value[name])
    assert isinstance(value["rationale"], str) and len(value["rationale"].strip()) >= 30
except Exception:
    print("WORKSPACE_TASK_INCOMPLETE")
    raise SystemExit(1)
print("schema ok")
"""


def harden_writing(root: Path) -> None:
    for spec in writing_specs():
        directory = root / task_id(spec)
        targets = spec.get("targets", ["sections/target.tex"])
        write(directory / "fixture" / "checks" / "check_content.py", WRITING_VISIBLE_CHECK.format(targets=targets))
        hidden = {
            "kind": "writing",
            "targets": targets,
            "reference_text": spec["reference"],
            "required_concepts": spec["required"],
            "forbidden_claims": spec["forbidden"],
            "purpose": "reference/adversarial admission only; real trajectories require blind semantic judging",
        }
        write_json(directory / "reference" / "hidden_spec.json", hidden)
        adversarial = directory / "reference" / "adversarial" / "surface-keywords"
        if adversarial.exists():
            shutil.rmtree(adversarial)
        surface = "Surface tokens only; this deliberately does not state a supported claim: " + "; ".join(spec["required"]) + "."
        for target in targets:
            write(adversarial / target, latex(surface) + "\n")
        task_path = directory / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["prompt"] = task["prompt"].replace("run both the content and LaTeX checks", "run the format and LaTeX checks")
        task["completion_criteria"][0]["description"] = "The Agent-visible format check passes without revealing the target claim."
        task["evaluation_visibility"] = {"agent_visible": ["format", "latex_compile"], "hidden": ["claim_strength", "evidence_use", "required_optional_actions"]}
        write_json(task_path, task)
        write(directory / "prompt.md", task["prompt"] + "\n")


def harden_reviews(root: Path) -> None:
    for spec in review_specs():
        directory = root / task_id(spec)
        write(directory / "fixture" / "checks" / "check_review.py", REVIEW_VISIBLE_CHECK)
        hidden = {
            "kind": "review",
            "decision": spec["decision"],
            "required_evidence_ids": spec["evidence"],
            "forbidden_required_actions": spec["forbidden"],
            "reference_rationale": spec["rationale"],
            "purpose": "reference/adversarial admission only; real trajectories require blind semantic judging",
        }
        write_json(directory / "reference" / "hidden_spec.json", hidden)
        adversarial = directory / "reference" / "adversarial" / "wrong-decision"
        if adversarial.exists():
            shutil.rmtree(adversarial)
        wrong = "reject" if spec["decision"] != "reject" else "accept"
        value = {
            "decision": wrong,
            "evidence_ids": spec["evidence"],
            "required_actions": spec["forbidden"],
            "optional_actions": [],
            "rationale": "This deliberately reaches the wrong decision while satisfying the public JSON schema.",
        }
        write_json(adversarial / "review.json", value)
        task_path = directory / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["completion_criteria"][0]["description"] = "The Agent-visible review schema check passes without revealing the target decision."
        task["evaluation_visibility"] = {"agent_visible": ["json_schema", "artifact_exists"], "hidden": ["decision", "evidence_selection", "required_optional_actions"]}
        write_json(task_path, task)


def harden_code(root: Path) -> None:
    for spec in code_specs():
        directory = root / task_id(spec)
        adversarial = directory / "reference" / "adversarial" / "known-wrong"
        if adversarial.exists():
            shutil.rmtree(adversarial)
        write(adversarial / "src" / spec["module"], spec["stub"])
        task_path = directory / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["evaluation_visibility"] = {"agent_visible": ["behavioral_checks"], "hidden": ["known_wrong_solution_rejection"]}
        write_json(task_path, task)

    streaming = root / "workspace-v0.2--code-native--streaming-zip-required"
    check = """import builtins
import inspect
import tempfile
from pathlib import Path
from zipfile import ZipFile
from src.archive import write_zip

class GuardedReader:
    def __init__(self, handle): self.handle = handle
    def read(self, size=-1):
        if size < 0 or size > 1024 * 1024: raise AssertionError("unbounded source read")
        return self.handle.read(size)
    def __enter__(self): return self
    def __exit__(self, *args): self.handle.close()
    def __getattr__(self, name): return getattr(self.handle, name)

try:
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); a=root/'a.json'; b=root/'b.bin'; a.write_text('{"x":1}',encoding='utf-8'); b.write_bytes(b'x'*(2*1024*1024+3))
        original_open=builtins.open
        def guarded_open(path, mode='r', *args, **kwargs):
            handle=original_open(path,mode,*args,**kwargs)
            return GuardedReader(handle) if Path(path)==b and 'rb' in mode else handle
        builtins.open=guarded_open
        try:
            out=root/'out.zip'; write_zip([('data/a.json',a),('b.bin',b)],out)
        finally:
            builtins.open=original_open
        with ZipFile(out) as z: assert z.namelist()==['data/a.json','b.bin'] and len(z.read('b.bin'))==len(b.read_bytes())
        for bad in ('../x','/abs'):
            try: write_zip([(bad,a)],root/'bad.zip')
            except ValueError: pass
            else: raise AssertionError('unsafe name accepted')
        try: write_zip([('a.json',a)],root/'missing'/'out.zip')
        except OSError: pass
        else: raise AssertionError('write failure was swallowed')
        source=inspect.getsource(write_zip)
        assert '.read_bytes(' not in source
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
"""
    write(streaming / "fixture" / "checks" / "check.py", check)

    bad = """from pathlib import PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED

def write_zip(entries, output_path):
    checked=list(entries)
    if any(PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts for name,_ in checked): raise ValueError('unsafe')
    with ZipFile(output_path,'w',compression=ZIP_DEFLATED) as zf:
        for name,source in checked: zf.writestr(name, source.read_bytes())
"""
    write(streaming / "reference" / "adversarial" / "known-wrong" / "src" / "archive.py", bad)


def main() -> int:
    root = TRACK / "tasks"
    harden_code(root); harden_writing(root); harden_reviews(root)
    print("hardened 50 tasks: hidden semantic oracles, generic visible checks, and known-wrong alternatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
