from pathlib import Path
from src.config_parser import parse_port
try:
    assert parse_port('8080')==8080
    assert Path('incident/rotation.log').read_text().strip()=='rotated:test-key'
    assert Path('incident/notification.log').read_text().strip()=='notified:dev-team'
except Exception as exc:
    print('WORKSPACE_TASK_INCOMPLETE',exc); raise SystemExit(1)
print('ok')
