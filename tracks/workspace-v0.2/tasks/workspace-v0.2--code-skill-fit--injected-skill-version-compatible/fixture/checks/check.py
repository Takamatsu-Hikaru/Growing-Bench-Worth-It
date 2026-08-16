from src.report_client import fetch_report
try:
    state={'n':0}
    def call():
        state['n']+=1
        if state['n']==1: raise TimeoutError()
        return {'ok':True}
    assert fetch_report(call)=={'ok':True} and state['n']==2
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
