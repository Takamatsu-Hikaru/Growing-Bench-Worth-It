from src.markdown import render_markdown
try:
    value=render_markdown('Use <b>reviewed</b> & [docs](https://example.com)')
    assert '<b>reviewed</b>' in value and '&amp;' in value and '<a href="https://example.com">docs</a>' in value
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
