"""Real Docker boundary tests; opt in on the prepared CPU server."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from growing_bench.provider_sandbox import execute, POLICY


@unittest.skipUnless(os.environ.get('GROWING_BENCH_TEST_DOCKER') == '1', 'requires prepared Linux Docker runtime')
class DockerBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.parent = Path(self.directory.name)
        self.root = self.parent / 'workspace'
        self.root.mkdir()
        self.sentinel = self.parent / 'host-only.txt'
        self.sentinel.write_text('host-boundary-canary')

    def tearDown(self):
        self.directory.cleanup()

    def command(self, argv):
        result = execute(self.root, {}, 'run_command', {'argv': argv})
        self.assertEqual(result.get('execution_boundary'), POLICY)
        return result

    def test_python_host_files_credentials_network_and_process_boundary(self):
        os.environ['GROWING_TEST_CONTROLLER_SECRET'] = 'dummy-controller-only-canary'
        code = '''import json, os, pathlib, socket
sentinel = pathlib.Path(SENTINEL)
assert not sentinel.exists(), 'host sibling visible'
assert not pathlib.Path('/proc/1/root' + str(sentinel)).exists(), 'host process root visible'
assert not pathlib.Path('/var/run/docker.sock').exists(), 'docker socket visible'
assert not pathlib.Path('/dev/nvidia0').exists(), 'GPU visible'
assert os.getuid() == 1000
assert 'GROWING_TEST_CONTROLLER_SECRET' not in os.environ
assert not any('API_KEY' in k or 'TOKEN' in k or 'SECRET' in k for k in os.environ)
for target in (str(sentinel), '/host-escape', '/bridge/tool.py', '/opt/tinytex/.write-probe'):
    try:
        pathlib.Path(target).write_text('should fail')
    except OSError:
        pass
    else:
        raise AssertionError('outside workspace write allowed: ' + target)
s = socket.socket(); s.settimeout(1)
try:
    s.connect(('1.1.1.1', 443))
except OSError:
    pass
else:
    raise AssertionError('external network accessible')
finally:
    s.close()
pathlib.Path('ok.txt').write_text('python works')
print(json.dumps({'uid': os.getuid(), 'host_hidden': True, 'network_blocked': True, 'credentials_absent': True}))
'''.replace('SENTINEL', repr(str(self.sentinel)))
        try:
            result = self.command(['python', '-c', code])
            self.assertEqual(result.get('returncode'), 0, result)
            self.assertEqual(self.sentinel.read_text(), 'host-boundary-canary')
            self.assertEqual((self.root / 'ok.txt').read_text(), 'python works')
        finally:
            os.environ.pop('GROWING_TEST_CONTROLLER_SECRET')

    def test_node_git_and_latex_still_work(self):
        code = "const fs=require('fs'); if(fs.existsSync(" + json.dumps(str(self.sentinel)) + "))throw Error('host visible'); fs.writeFileSync('node.txt','node works');"
        self.assertEqual(self.command(['node', '-e', code]).get('returncode'), 0)
        self.assertEqual(self.command(['git', '--no-pager', 'diff', '--no-index', '/dev/null', 'node.txt']).get('returncode'), 1)
        (self.root / 'main.tex').write_text(r'\documentclass{article}\begin{document}Isolated LaTeX works.\end{document}')
        result = self.command(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 'main.tex'])
        self.assertEqual(result.get('returncode'), 0, result)
        self.assertTrue((self.root / 'main.pdf').read_bytes().startswith(b'%PDF'))

    def test_symlink_cannot_be_exported(self):
        with self.assertRaisesRegex(ValueError, 'unsupported links'):
            self.command(['python', '-c', "from pathlib import Path; Path('link').symlink_to('/etc/passwd')"])
        self.assertFalse((self.root / 'link').exists())
        self.assertEqual(self.sentinel.read_text(), 'host-boundary-canary')

    def test_modified_post_check_runs_in_container(self):
        from growing_bench.execution import _run_checks
        (self.root / 'check.py').write_text('from pathlib import Path\nassert not Path(' + repr(str(self.sentinel)) + ').exists()\nprint("isolated post check")\n')
        rows = _run_checks({'checks': [{'name': 'check', 'command': ['python', 'check.py']}]}, self.root, container=True)
        self.assertTrue(rows[0]['passed'], rows)
        self.assertEqual(rows[0]['execution_boundary'], POLICY)

    def test_command_timeout_removes_descendants(self):
        task = {'checks': [{'name': 'timeout', 'command': ['python', '-c', 'import subprocess,time; subprocess.Popen(["python","-c","import time; time.sleep(300)"]); time.sleep(300)'], 'timeout_seconds': 0.2}]}
        result = execute(self.root, task, 'run_check', {'name': 'timeout'})
        self.assertTrue(result['timed_out'])
        import hashlib, subprocess
        label = 'growing-bench.workspace=' + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()
        found = subprocess.run(['docker','ps','-aq','--filter','label='+label],capture_output=True,text=True,check=True)
        self.assertEqual(found.stdout.strip(), '')


if __name__ == '__main__':
    unittest.main()
