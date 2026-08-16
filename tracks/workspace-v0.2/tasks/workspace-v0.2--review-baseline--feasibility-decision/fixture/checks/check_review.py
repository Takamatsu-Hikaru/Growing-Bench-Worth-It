import json
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
