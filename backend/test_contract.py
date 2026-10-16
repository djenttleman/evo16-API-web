"""API/security, current USB encoding, failure recovery and multi-client behavior. No hardware."""
import copy
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend import main, presets
from backend.runtime import DeviceRuntime, Unavailable
from backend.service import Evo16Service, PROTOCOL_VERSION, DeviceConnectionError
from backend.test_presets import channels

TOKEN = "t" * 43
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeDevice:
    def __init__(self):
        self._connected = False
        self.reads = self.meter_reads = self.writes = 0
        self.values = channels()
    def connect(self): self._connected = True
    def disconnect(self): self._connected = False
    def health(self): return {"connected": self._connected, "helper": self._connected, "mainVolume": -20}
    def get_all_status(self):
        self.reads += 1
        return {"device": "Fake EVO 16", "inputs": copy.deepcopy(self.values), "outputs": [], "mainVolume": -20}
    def set_gain(self, channel, value):
        self.writes += 1; self.values[channel - 1]["gain"] = value
        return value
    def get_gain(self, channel): return self.values[channel - 1]["gain"]
    def get_meters(self):
        self.meter_reads += 1
        return {"inputs": [0] * 24, "outputs": [0] * 16}


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.device = FakeDevice()
        self.runtime = DeviceRuntime(lambda: self.device)
        self.patches = [patch.object(main, "api_token", return_value=TOKEN),
                        patch.object(main, "DeviceRuntime", return_value=self.runtime),
                        patch.object(presets, "PRESETS_DIR", Path(self.temp.name)),
                        patch("backend.runtime.subprocess.run", return_value=SimpleNamespace(returncode=1))]
        for p in self.patches: p.start()
        self.client = TestClient(main.app, base_url="http://127.0.0.1:3000", client=("127.0.0.1", 5000)).__enter__()
        self.runtime.submit(lambda: None)  # Wait until startup connection attempt completes.

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_authentication_and_host_origin_protection(self):
        self.assertEqual(self.client.get('/api/health').status_code, 401)
        self.assertEqual(self.client.get('/api/health', headers=AUTH).status_code, 200)
        for extra, expected in [({'Host': 'evil.example'}, 400),
                                 ({'Origin': 'https://evil.example'}, 403),
                                 ({'Sec-Fetch-Site': 'cross-site'}, 403)]:
            self.assertEqual(self.client.get('/api/health', headers={**AUTH, **extra}).status_code, expected)
        # Network UI does not receive the local cookie.
        remote = TestClient(main.app, base_url='http://192.168.1.10:3000', client=('192.168.1.22', 5000))
        self.assertNotIn('set-cookie', remote.get('/').headers)

    def test_cookie_session_requires_same_origin_for_writes(self):
        r = self.client.get('/')
        self.assertIn('HttpOnly', r.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.post('/api/gain/1', json={'db': 20}).status_code, 401)
        self.assertEqual(self.client.post('/api/gain/1', json={'db': 20},
            headers={'Origin': 'http://127.0.0.1:3000'}).status_code, 200)

    def test_no_path_traversal_or_arbitrary_filesystem_api(self):
        for path in ['/%2e%2e/README.md', '/%2e%2e/backend/main.py', '/%2fetc/passwd']:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post('/api/presets/import', headers=AUTH,
                                        json={'path': '/etc/passwd'}).status_code, 422)
        r = self.client.post('/api/presets/import', headers=AUTH,
            content=b'x' * (256 * 1024 + 1))
        self.assertEqual(r.status_code, 413)

    def test_offline_writes_never_succeed_and_reconnect_recovers(self):
        self.runtime.submit(self.device.disconnect)
        for path, body in [('/api/gain/1', {'db': 0}), ('/api/phantom/1', {'on': True}),
                           ('/api/mute/1', {'muted': False}), ('/api/main-volume', {'db': -20})]:
            self.assertEqual(self.client.post(path, headers=AUTH, json=body).status_code, 503)
        self.assertEqual(self.device.writes, 0)
        r = self.client.post('/api/reconnect', headers=AUTH)
        self.assertTrue(r.json()['ok'])

    def test_current_gain_contract_and_validation(self):
        for value in [-8, 0, 50]:
            r = self.client.post('/api/gain/1', headers=AUTH, json={'db': value})
            self.assertEqual(r.json()['gain'], value)
        for value in [-9, 51, True, '20']:
            self.assertEqual(self.client.post('/api/gain/1', headers=AUTH, json={'db': value}).status_code, 422)
        self.assertEqual(self.client.get('/api/instrument/3', headers=AUTH).status_code, 400)
        self.assertEqual(self.client.post('/api/main-volume', headers=AUTH, json={'db': 1}).status_code, 422)
        schema = self.client.get('/api/openapi.json', headers=AUTH).json()
        self.assertEqual(schema['info']['version'], '2.0.0')
        for name in ['gain', 'mute', 'phantom']:
            self.assertIn('get', schema['paths'][f'/api/{name}/{{channel}}'])

    def test_shared_status_and_meter_cache_invalidate_on_write(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.runtime.status(), range(8)))
        self.assertEqual(self.device.reads, 1)
        self.assertTrue(all(r['sampleAgeSeconds'] < 1 for r in results))
        self.runtime.call('set_gain', 1, -8, write=True)
        self.assertEqual(self.runtime.status()['inputs'][0]['gain'], -8)
        self.assertEqual(self.device.reads, 2)
        for _ in range(8): self.runtime.meter_values()
        self.assertEqual(self.device.meter_reads, 1)

    def test_profile_validation_precedes_any_hardware_operation(self):
        data = {'name': 'Malo', 'formatVersion': 2, 'gainEncoding': 'db', 'channels': channels()[:2]}
        self.assertEqual(self.client.post('/api/presets/import', headers=AUTH, json={'preset': data}).status_code, 400)
        self.assertEqual(self.device.writes, 0)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])


class WorkerTests(unittest.TestCase):
    def test_recovery_after_factory_initialization_failure(self):
        device = FakeDevice()
        calls = []
        def factory():
            calls.append(1)
            if len(calls) == 1: raise FileNotFoundError('helper missing temporarily')
            return device
        runtime = DeviceRuntime(factory, interval=0.02)
        with patch('backend.runtime.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            runtime.start()
            runtime.submit(lambda: None)
            self.assertFalse(runtime.health()['ok'])
            self.assertTrue(runtime.reconnect()['ok'])
            runtime.close()

    def test_absent_device_is_distinct_from_helper_failure_and_persists_during_backoff(self):
        fixture = str(Path(__file__).parent / 'fixtures/usb_helper.py')
        runtime = DeviceRuntime(lambda: Evo16Service(fixture), interval=0.02)
        with patch.dict(os.environ, {'EVO16_FIXTURE_OFFLINE': '1'}), \
             patch('backend.runtime.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            runtime.start()
            runtime.submit(lambda: None)
            self.assertEqual(runtime.health()['state'], 'device_disconnected')
            self.assertFalse(runtime.health()['ok'])
            time.sleep(0.1)
            self.assertEqual(runtime.health()['state'], 'device_disconnected')
            with self.assertRaises(Unavailable): runtime.status()
            runtime.close()

    def test_expired_queued_write_is_not_executed_and_health_stays_responsive(self):
        device = FakeDevice(); runtime = DeviceRuntime(lambda: device)
        with patch('backend.runtime.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            runtime.start(); runtime.submit(lambda: None)
            entered = threading.Event(); release = threading.Event()
            with ThreadPoolExecutor() as pool:
                blocked = pool.submit(runtime.submit, lambda: (entered.set(), release.wait(2)))
                self.assertTrue(entered.wait(1))
                begin = time.monotonic(); self.assertTrue(runtime.health()['ok'])
                self.assertLess(time.monotonic() - begin, 0.1)
                with self.assertRaises(Unavailable):
                    runtime.submit(lambda: device.set_gain(1, 40), timeout=0.02)
                release.set(); blocked.result()
            runtime.submit(lambda: None)
            self.assertEqual(device.writes, 0)
            runtime.close()


class ProtocolTests(unittest.TestCase):
    def setUp(self): self.device = Evo16Service(helper_path='/not-used')

    def test_latest_gain_offset(self):
        for db, byte in [(-8, 0), (0, 8), (50, 58)]:
            with patch.object(self.device, '_send', return_value={'status': 'ok'}) as send:
                self.assertEqual(self.device.set_gain(1, db), db)
                self.assertEqual(send.call_args.args[0]['data'], [0, byte, 0, 0])
            with patch.object(self.device, '_send', return_value={'data': [0, byte, 0, 0]}):
                self.assertEqual(self.device.get_gain(1), db)
        self.assertEqual(PROTOCOL_VERSION, 'evo16-2026-10-16')

    def test_di_preserves_other_bits_and_link_targets_cs3(self):
        with patch.object(self.device, '_send', side_effect=[{'data': [5, 0, 0, 0]}, {'status': 'ok'}]) as send:
            self.device.set_instrument(1, True)
            self.assertEqual(send.call_args_list[0].args[0]['wValue'], 4 << 8)
            self.assertEqual(send.call_args_list[1].args[0]['data'], [7, 0, 0, 0])
        with patch.object(self.device, '_send', return_value={'status': 'ok'}) as send:
            self.device.set_link(2, False)
            self.assertEqual([c.args[0]['wValue'] for c in send.call_args_list], [3 << 8, (3 << 8) | 1])

    def test_helper_deadline_discards_partial_response_and_closes_only_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'helper'
            script.write_text('#!/usr/bin/env python3\nimport time\nprint("READY", flush=True)\ninput()\nprint("{", end="", flush=True)\ntime.sleep(10)\n')
            script.chmod(0o755)
            device = Evo16Service(str(script)); device.connect()
            process = device._proc
            with self.assertRaises(TimeoutError): device.get_main_volume()
            self.assertFalse(device._connected)
            self.assertIsNotNone(process.poll())

    def test_linked_profile_does_not_duplicate_mirrored_writes(self):
        values = channels()
        for value in values: value['linked'] = True
        with patch.object(self.device, '_send', return_value={'status': 'ok', 'data': [0, 0, 0, 0]}) as send:
            result = self.device.apply_state(values)
            commands = [c.args[0] for c in send.call_args_list]
        self.assertFalse(result['errors'])
        gains = [c for c in commands if c['wIndex'] == 0x3A00 and c['wValue'] >> 8 == 1]
        self.assertEqual(len(gains), 12)
        # No read/modify/write for followers; 3 master DI channels instead of 6.
        flags = [c for c in commands if c['wIndex'] == 0x3A00 and c['wValue'] >> 8 == 4]
        # Mock get_cur must return data for the DI reads.
        self.assertEqual(len(flags), 6)

    def test_failed_snapshot_does_not_fabricate_channel_values(self):
        with patch.object(self.device, 'get_main_volume', return_value=-20), \
             patch.object(self.device, 'get_link', return_value=False), \
             patch.object(self.device, 'get_gain', side_effect=RuntimeError('USB read failed')):
            with self.assertRaisesRegex(RuntimeError, 'USB read failed'):
                self.device.get_all_status()

    def test_main_floor_and_no_positive_gain(self):
        with patch.object(self.device, '_send', return_value={'status': 'ok'}) as send:
            self.assertEqual(self.device.set_main_volume(-128), -128)
            self.assertEqual(send.call_args.args[0]['data'], [0, 128])
        with self.assertRaises(ValueError): self.device.set_main_volume(0.1)


if __name__ == '__main__': unittest.main()
