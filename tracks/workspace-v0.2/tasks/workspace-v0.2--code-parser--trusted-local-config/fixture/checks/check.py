from src.config import parse_config
try:
    assert parse_config('{"name":"job","workers":4,"future":true}')['future'] is True
    try: parse_config('{"name":"job","workers":0}')
    except ValueError: pass
    else: raise AssertionError('invalid workers accepted')
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
