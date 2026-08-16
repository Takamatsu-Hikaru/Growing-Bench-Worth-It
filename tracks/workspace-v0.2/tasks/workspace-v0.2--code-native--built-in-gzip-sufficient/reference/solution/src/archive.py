import gzip
import json

def write_json_gzip(payload, output_path):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    with gzip.open(output_path, 'wb') as handle:
        handle.write(raw)
