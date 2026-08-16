import json

def parse_upload(raw):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>4096: raise ValueError('size')
    value=json.loads(raw.decode('utf-8'))
    if not isinstance(value,dict) or set(value)!={'name','workers'}: raise ValueError('shape')
    if not isinstance(value['name'],str) or len(value['name'])>80: raise ValueError('name')
    if not isinstance(value['workers'],int) or not 1<=value['workers']<=32: raise ValueError('workers')
    return {'name':value['name'],'workers':value['workers']}
