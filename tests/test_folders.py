"""API каталогов: отдельная копия сервера/БД, никакого GUI и моделей."""
import json
import os
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import test_pipeline as fixture
import folders


class FolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = fixture.SANDBOX / "Папки с пробелами & ; $()"
        cls.root.mkdir()
        (cls.root / "Пустая").mkdir()
        (cls.root / "Текст.txt").write_text("test", encoding="utf-8")
        cls.srv = fixture.main.Server(("127.0.0.1", 0), fixture.main.Handler)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.srv.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join()

    def api(self, path, endpoint="/api/folders"):
        req = urllib.request.Request(self.base + endpoint, data=json.dumps({"path": path}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_roots_and_drive_change(self):
        code, data = self.api(None)
        self.assertEqual(code, 200)
        self.assertIsNone(data["path"])
        self.assertTrue(data["entries"])
        for entry in data["entries"]:
            self.assertTrue(os.path.isabs(entry["path"]))
        if os.name == "nt":
            self.assertTrue(any(e["path"].lower() == self.root.anchor.lower() for e in data["entries"]))

    def test_unicode_spaces_metacharacters_only_directories(self):
        code, data = self.api(str(self.root))
        self.assertEqual(code, 200)
        self.assertEqual(data["entries"], [{"name": "Пустая", "path": str(self.root / "Пустая")}])
        self.assertEqual(data["parent"], str(self.root.parent))
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"Пустая", "Текст.txt"})

    def test_empty_and_normalized_parent(self):
        code, data = self.api(str(self.root / "Пустая"))
        self.assertEqual(code, 200)
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["parent"], str(self.root))
        self.assertEqual(self.api(str(self.root / "Пустая" / ".."))[1]["path"], str(self.root))

    def test_long_path(self):
        path = fixture.SANDBOX / "long"
        for i in range(8):
            path = path / ("Длинный путь с пробелом " + str(i))
        Path(folders.native_path(str(path))).mkdir(parents=True)
        self.assertGreater(len(str(path)), 260)
        self.assertEqual(self.api(str(path))[0], 200)

    def test_missing_removed_and_file(self):
        for path in (self.root / "Нет", self.root / "Текст.txt"):
            self.assertEqual(self.api(str(path))[0], 404)
        path = self.root / "Удалённая"
        path.mkdir()
        self.assertEqual(self.api(str(path))[0], 200)
        path.rmdir()
        self.assertEqual(self.api(str(path))[0], 404)

    def test_invalid_input(self):
        for path in ("", "relative", "a\x00b", 3, {}, [], "x" * 32761):
            with self.subTest(path=repr(path)[:30]):
                self.assertEqual(self.api(path)[0], 400)
        if os.name == "nt":
            for path in ("C:relative", "\\Projects", "\\\\?\\C:\\", "\\\\.\\C:\\", "C:\\file:stream"):
                self.assertEqual(self.api(path)[0], 400)

    def test_permission_and_unavailable_worker_responses(self):
        # Реальные ACL тестовой машины не меняем; проверяем перевод ошибок в worker.
        for exc, expected in ((PermissionError(), 403), (OSError(), 503), (FileNotFoundError(), 404)):
            with patch.object(folders.sys, "stdin") as stdin, patch.object(folders.sys, "stdout") as stdout:
                stdin.buffer.read.return_value = json.dumps({"path": str(self.root)}).encode()
                with patch.object(folders.os, "scandir", side_effect=exc):
                    folders.worker()
                self.assertEqual(json.loads(stdout.buffer.write.call_args.args[0])["code"], expected)

    def test_timeout_and_busy_are_bounded(self):
        with patch.object(fixture.main.runtime, "run", side_effect=subprocess.TimeoutExpired("worker", 5)) as run:
            self.assertEqual(self.api(str(self.root))[0], 504)
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
            self.assertNotIn(str(self.root), run.call_args.args[0])
        with patch.object(folders, "SLOTS") as slots:
            slots.acquire.return_value = False
            self.assertEqual(self.api(None)[0], 429)
        self.assertEqual(self.api(None)[0], 200)

    def test_old_endpoint_never_opens_desktop_dialog(self):
        with patch.object(fixture.main.runtime, "run") as run:
            self.assertEqual(self.api(None, "/api/pick-folder")[0], 404)
            run.assert_not_called()

    def test_actual_worker_timeout_leaves_no_process(self):
        before = set(fixture.main.runtime.processes)
        with patch.object(folders, "TIMEOUT", .001):
            self.assertEqual(self.api(None)[0], 504)
        self.assertEqual(set(fixture.main.runtime.processes), before)

    def test_project_create_update_long_path_and_deleted_selection(self):
        path = fixture.SANDBOX / "long-project"
        for i in range(13):
            path /= "Длинная папка " + str(i)
        Path(folders.native_path(str(path))).mkdir(parents=True)
        self.assertGreater(len(str(path)), 260)
        main = fixture.main
        data = main.api_project_create(None, {"name": "Длинный проект", "path": str(path)}, {})
        self.assertEqual(data["path"], str(path))
        main.api_project_update(None, {"path": str(self.root)}, {}, data["id"])
        Path(folders.native_path(str(path))).rmdir()
        with self.assertRaises(main.HttpError) as error:
            main.api_project_update(None, {"path": str(path)}, {}, data["id"])
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
