from __future__ import annotations

import json
import sys
from pathlib import Path


def _write_csv_solution(workspace: Path) -> bool:
    target = workspace / "src" / "report_export.py"
    helper = workspace / "src" / "csv_support.py"
    if not target.is_file() or not helper.is_file():
        return False
    target.write_text(
        "from .csv_support import serialize_csv\n\n"
        "def export_report(rows):\n"
        "    selected = [{key: row[key] for key in ('id', 'name', 'note')} for row in rows]\n"
        "    return serialize_csv(['id', 'name', 'note'], selected)\n",
        encoding="utf-8", newline="\n",
    )
    return True


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: python -m growing_bench.demo_interactive_agent WORKSPACE PROMPT_FILE TURN_INDEX")
    workspace = Path(sys.argv[1]).resolve()
    prompt = Path(sys.argv[2]).read_text(encoding="utf-8")
    turn_index = int(sys.argv[3])
    changed = _write_csv_solution(workspace) if turn_index == 1 else False
    if turn_index == 1:
        final = "Implemented the requested CSV export by reusing the repository serializer and kept the change inside src/report_export.py."
    else:
        final = "Understood. The current implementation already follows that constraint, so I left the workspace unchanged."
    events = [{
        "kind": "file_write" if changed else "assistant_message",
        "content": "Updated src/report_export.py" if changed else final,
        "target": "src/report_export.py" if changed else None,
        "status": "success",
    }]
    print(json.dumps({"final": final, "events": events, "usage": {"total_tokens": len(prompt.split())}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
