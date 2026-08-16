import json
_CACHE={}

def load_catalog(path):
    key=str(path.resolve()); stamp=path.stat().st_mtime_ns; row=_CACHE.get(key)
    if row and row[0]==stamp: return row[1]
    value=json.loads(path.read_text(encoding='utf-8')); _CACHE.clear(); _CACHE[key]=(stamp,value); return value
