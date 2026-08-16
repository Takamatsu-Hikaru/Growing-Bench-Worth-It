import tempfile, json
from pathlib import Path
from src.settings import get_setting
try:
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'s.json'; p.write_text('{"mode":"a"}')
        assert get_setting(p,'mode')=='a'; p.write_text('{"mode":"b"}'); assert get_setting(p,'mode')=='b'
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
