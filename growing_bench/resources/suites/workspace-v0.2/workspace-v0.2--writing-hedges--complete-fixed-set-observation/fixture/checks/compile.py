import shutil, subprocess
if not shutil.which('pdflatex'):
    print('pdflatex unavailable'); raise SystemExit(2)
raise SystemExit(subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex']).returncode)
