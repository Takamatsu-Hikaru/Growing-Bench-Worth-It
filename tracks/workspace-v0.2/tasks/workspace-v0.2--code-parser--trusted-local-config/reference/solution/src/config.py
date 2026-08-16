import json

def parse_config(text):
    value=json.loads(text)
    if not isinstance(value.get('name'),str): raise ValueError('name')
    if not isinstance(value.get('workers'),int) or not 1<=value['workers']<=32: raise ValueError('workers')
    return value
