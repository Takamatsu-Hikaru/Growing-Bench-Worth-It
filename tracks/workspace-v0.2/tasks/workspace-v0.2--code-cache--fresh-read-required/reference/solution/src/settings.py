import json

def get_setting(path,key):
    return json.loads(path.read_text(encoding='utf-8'))[key]
