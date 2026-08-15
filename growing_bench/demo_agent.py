from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m growing_bench.demo_agent WORKSPACE")
    workspace = Path(sys.argv[1]).resolve()
    (workspace / "answer.txt").write_text("done\n", encoding="utf-8", newline="\n")
    print(json.dumps({"final": "Created answer.txt and kept the change within the allowed scope."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
