import html, re

def render_markdown(text):
    escaped=html.escape(text,quote=True)
    escaped=re.sub(r'\[([^]]+)\]\((https://[^)]+)\)', r'<a href="\2">\1</a>', escaped)
    escaped=re.sub(r'\[([^]]+)\]\((?:javascript|data):[^)]+\)', r'\1', escaped, flags=re.I)
    return '<p>'+escaped+'</p>'
