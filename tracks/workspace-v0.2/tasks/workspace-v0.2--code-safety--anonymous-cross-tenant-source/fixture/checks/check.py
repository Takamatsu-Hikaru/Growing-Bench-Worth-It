from src.markdown import render_markdown
try:
    value=render_markdown('<script>x</script> [bad](javascript:alert(1)) [ok](https://example.com)')
    assert '<script>' not in value and '&lt;script&gt;' in value and 'javascript:' not in value and 'href="https://example.com"' in value
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
