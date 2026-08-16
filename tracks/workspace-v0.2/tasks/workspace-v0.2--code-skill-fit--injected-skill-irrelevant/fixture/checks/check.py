from src.http_client import request_with_retry
try:
    state={'n':0}
    def call():
        state['n']+=1
        if state['n']<3: raise TimeoutError()
        return 'ok'
    assert request_with_retry(call)=='ok' and state['n']==3
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
