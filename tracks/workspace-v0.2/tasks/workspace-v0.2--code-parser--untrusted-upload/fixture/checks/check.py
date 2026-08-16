from src.upload import parse_upload
try:
    assert parse_upload(b'{"name":"job","workers":4}')=={'name':'job','workers':4}
    for raw in (b'{}',b'{"name":"x","workers":2,"admin":true}',b'x'*4097):
        try: parse_upload(raw)
        except (ValueError,UnicodeDecodeError): pass
        else: raise AssertionError('unsafe upload accepted')
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
