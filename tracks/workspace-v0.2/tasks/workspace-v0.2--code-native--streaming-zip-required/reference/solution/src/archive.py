from pathlib import PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED

def _safe(name):
    p=PurePosixPath(name)
    return bool(name) and not p.is_absolute() and '..' not in p.parts

def write_zip(entries, output_path):
    checked=list(entries)
    if any(not _safe(name) for name,_ in checked):
        raise ValueError('unsafe entry name')
    with ZipFile(output_path,'w',compression=ZIP_DEFLATED) as zf:
        for name,source in checked:
            with zf.open(name,'w') as target, open(source,'rb') as handle:
                while True:
                    chunk=handle.read(1024*1024)
                    if not chunk: break
                    target.write(chunk)
