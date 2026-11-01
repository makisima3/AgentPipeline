"""Остановка отдельного процесса: порт, блокировка, деревья и сохранность SQLite."""
import concurrent.futures
import json
import os
import socket
import sqlite3
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from shutdown_demo import launch


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.proc, self.root, self.port = launch()
        self.base = f"http://127.0.0.1:{self.port}"
        self.boot = self.api('/api/state')[1]['boot_id']

    def tearDown(self):
        if self.proc.poll() is None:
            try:
                self.stop()
                self.proc.wait(30)
            finally:
                if self.proc.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'], capture_output=True)
                    else:
                        self.proc.kill()

    def api(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def stop(self):
        return self.api('/api/shutdown', {'confirm': True}, {'X-AgentPipeline-Stop': self.boot, 'Origin': self.base})

    def assert_stopped(self):
        self.assertEqual(self.proc.wait(35), 0, (self.root / 'demo.log').read_text(encoding='utf-8'))
        with socket.socket() as sock:
            self.assertNotEqual(sock.connect_ex(('127.0.0.1', self.port)), 0)
        conn = sqlite3.connect(self.root / 'data/tracker.db')
        self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(conn.execute("SELECT value FROM settings WHERE key='pipeline_enabled'").fetchone()[0], '0')
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM task_results').fetchone()[0], 1)
        files = json.loads(conn.execute('SELECT files FROM task_results').fetchone()[0])
        self.assertEqual((self.root / 'data/results' / files[0]['path']).read_text(encoding='utf-8'), 'Материал сохранён до остановки')
        conn.close()

    def test_confirmation_access_idle_and_manual_restart(self):
        self.assertEqual(self.api('/api/shutdown', {'confirm': True})[0], 403)
        header = {'X-AgentPipeline-Stop': self.boot}
        self.assertEqual(self.api('/api/shutdown', {'confirm': True}, {**header, 'Origin': 'https://other.invalid'})[0], 403)
        self.assertEqual(self.api('/api/shutdown', {'confirm': False}, header)[0], 400)
        self.assertEqual(self.api('/api/shutdown')[1]['status'], 'running')
        self.assertEqual(self.stop()[0], 200)
        self.assert_stopped()
        self.proc, _, _ = launch(self.root, self.port)
        state = self.api('/api/state')[1]
        self.assertNotEqual(state['boot_id'], self.boot)
        self.assertEqual(state['shutdown'], 'running')
        self.assertEqual(state['pipeline']['enabled'], '0')
        self.boot = state['boot_id']

    def test_active_work_repeat_and_pending_restart(self):
        data = self.api('/api/demo/work', {})[1]
        self.assertEqual(len(data['pids']), 12)
        self.assertEqual(self.api('/api/restart', {})[0], 200)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            responses = list(pool.map(lambda _: self.stop(), range(4)))
        self.assertTrue(all(code == 200 for code, _ in responses))
        self.assertEqual(self.api('/api/settings', {'pipeline_enabled': '1'})[0], 409)
        self.assert_stopped()
        conn = sqlite3.connect(self.root / 'data/tracker.db')
        self.assertEqual(conn.execute('SELECT status FROM tasks WHERE id=?', (data['task_id'],)).fetchone()[0], 'interrupted')
        self.assertGreater(conn.execute('SELECT COUNT(*) FROM chat_messages WHERE chat_id=?', (data['chat_id'],)).fetchone()[0], 0)
        conn.close()
        if os.name == 'nt':
            import ctypes
            kernel = ctypes.windll.kernel32
            for pid in data['pids']:
                handle = kernel.OpenProcess(0x00100000, False, pid)
                if handle:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0, f'Остался процесс {pid}')
                    kernel.CloseHandle(handle)

    def test_inflight_service_request_finishes_before_database_close(self):
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.api, '/api/demo/slow', {})
            for _ in range(100):
                if (self.root / 'slow-started').exists():
                    break
                time.sleep(.05)
            self.assertTrue((self.root / 'slow-started').exists())
            self.assertEqual(self.stop()[0], 200)
            code, result = future.result(timeout=20)
            self.assertEqual(code, 200)
        self.assert_stopped()
        conn = sqlite3.connect(self.root / 'data/tracker.db')
        self.assertEqual(conn.execute('SELECT title FROM tasks WHERE id=?', (result['task_id'],)).fetchone()[0], 'Квитанция прерванного импорта')
        conn.close()


if __name__ == '__main__':
    unittest.main()
