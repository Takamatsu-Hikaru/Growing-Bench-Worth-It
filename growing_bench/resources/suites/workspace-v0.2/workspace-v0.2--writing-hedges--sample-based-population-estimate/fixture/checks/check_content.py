from pathlib import Path

TARGETS = ['sections/target.tex']
try:
    values = [Path(path).read_text(encoding="utf-8").strip() for path in TARGETS]
    assert values and all(len(value) >= 30 for value in values)
    assert all("WORKSPACE TASK INCOMPLETE" not in value for value in values)
except Exception:
    print("WORKSPACE_TASK_INCOMPLETE")
    raise SystemExit(1)
print("format ok")
