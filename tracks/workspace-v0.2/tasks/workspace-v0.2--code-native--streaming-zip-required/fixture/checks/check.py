import builtins
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
