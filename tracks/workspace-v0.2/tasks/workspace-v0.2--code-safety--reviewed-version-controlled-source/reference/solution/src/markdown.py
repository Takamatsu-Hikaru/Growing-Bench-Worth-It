import re

def render_markdown(text):
    text=re.sub(r'&(?![a-zA-Z]+;)', '&amp;', text)
    text=re.sub(r'\[([^]]+)\]\((https://[^)]+)\)', r'<a href="\2">\1</a>', text)
    return '<p>'+text+'</p>'
