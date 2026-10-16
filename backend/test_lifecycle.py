"""Real HTTP/process checks with an explicitly selected helper fixture; never touches USB."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LifecycleTests(unittest.TestCase):
    def test_source_and_optional_frozen_service(self):
        executables = [[sys.executable, str(ROOT / 'backend/main.py')]]
        frozen = ROOT / 'build/EVO 16 Remote.app/Contents/Resources/service/EVO16Service'
        if frozen.exists(): executables.append([str(frozen)])
        for command in executables:
            with self.subTest(executable=command[0]), tempfile.TemporaryDirectory() as temp:
                port = free_port()
                parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
                environment = {**os.environ, 'EVO16_PORT': str(port), 'EVO16_HOST': '127.0.0.1',
                    'EVO16_DATA_DIR': temp, 'EVO16_PARENT_PID': str(parent.pid),
                    'EVO16_HELPER_PATH': str(ROOT / 'backend/fixtures/usb_helper.py')}
                environment.pop('EVO16_API_TOKEN', None)
                process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                def fetch(path, auth=True):
                    headers = {}
                    if auth: headers['Authorization'] = 'Bearer ' + (Path(temp) / 'api-token').read_text()
                    return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers), timeout=2)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            with fetch('/api/health') as response:
                                if json.load(response)['ok']: break
                        except (OSError, KeyError, ValueError): pass
                        if time.monotonic() > deadline: self.fail('El proceso no respondió a tiempo')
                        time.sleep(0.1)
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        fetch('/api/health', auth=False)
                    self.assertEqual(caught.exception.code, 401)
                    with fetch('/api/status') as response:
                        status = json.load(response)
                        self.assertEqual(status['inputs'][0]['gain'], 0)
                        self.assertEqual(len(status['inputs']), 24)
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        fetch('/%2e%2e/README.md')
                    self.assertEqual(caught.exception.code, 404)
                    self.assertEqual((Path(temp) / 'api-token').stat().st_mode & 0o777, 0o600)
                    # A second instance fails without terminating the existing service.
                    duplicate = subprocess.run(command, env={**environment, 'EVO16_PORT': str(free_port())},
                                               capture_output=True, timeout=5)
                    self.assertNotEqual(duplicate.returncode, 0)
                    with fetch('/api/health') as response: self.assertEqual(response.status, 200)
                    # Loss of the owning app shuts down the worker and its helper.
                    parent.terminate(); parent.wait(timeout=2)
                    process.wait(timeout=8)
                    self.assertEqual(process.returncode, 0)
                    with socket.socket() as sock:
                        self.assertNotEqual(sock.connect_ex(('127.0.0.1', port)), 0)
                finally:
                    if parent.poll() is None: parent.terminate(); parent.wait(timeout=2)
                    if process.poll() is None: process.terminate()
                    try: output = process.communicate(timeout=5)[0]
                    except subprocess.TimeoutExpired: process.kill(); output = process.communicate()[0]
                    if process.returncode not in (0, -signal.SIGTERM):
                        print(output.decode(errors='replace'))


if __name__ == '__main__': unittest.main()
