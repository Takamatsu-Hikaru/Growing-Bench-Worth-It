import gzip, json, tempfile
from pathlib import Path
from src.archive import write_json_gzip
try:
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'out.json.gz'; value={'name':'路线','items':[1,2]}; write_json_gzip(value,p)
        assert json.loads(gzip.decompress(p.read_bytes()).decode('utf-8'))==value
        try: write_json_gzip(value,Path(d)/'missing'/'out.gz')
        except OSError: pass
        else: raise AssertionError('write failure was swallowed')
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
