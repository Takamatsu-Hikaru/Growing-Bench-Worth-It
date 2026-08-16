import tempfile, os, time
from pathlib import Path
from src.catalog import load_catalog, _CACHE
try:
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'c.json'; p.write_text('{"v":1}'); first=load_catalog(p); second=load_catalog(p); assert first is second and len(_CACHE)==1
        time.sleep(0.01); p.write_text('{"v":2}'); os.utime(p,None); assert load_catalog(p)['v']==2 and len(_CACHE)==1
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
