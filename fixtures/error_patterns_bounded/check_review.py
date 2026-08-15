from pathlib import Path
p = Path('review.md')
if not p.is_file() or len(p.read_text(encoding='utf-8').strip()) < 120:
    raise SystemExit('review.md is missing or too short')
print('review artifact present')
