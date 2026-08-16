from pathlib import PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED

def write_zip(entries, output_path):
    checked=list(entries)
    if any(PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts for name,_ in checked): raise ValueError('unsafe')
    with ZipFile(output_path,'w',compression=ZIP_DEFLATED) as zf:
        for name,source in checked: zf.writestr(name, source.read_bytes())
