from pathlib import Path

path = Path("answer.txt")
if not path.is_file():
    raise SystemExit("answer.txt is missing")
if path.read_text(encoding="utf-8") != "done\n":
    raise SystemExit("answer.txt must contain exactly done followed by a newline")
print("adapter smoke passed")
