from src.report_export import export_report
try:
    value=export_report([{'id':'1','name':'A, "B"','note':'line1\r\n路线'}])
    assert value.startswith('id,name,note\r\n') and '"A, ""B"""' in value and value.endswith('\r\n')
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
