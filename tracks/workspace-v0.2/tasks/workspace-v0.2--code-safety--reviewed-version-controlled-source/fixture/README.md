# Render reviewed Markdown without redundant sanitization

All Markdown is reviewed in the same repository. Policy allows inline <b> tags and https links. The renderer must escape plain ampersands while preserving those reviewed constructs.
