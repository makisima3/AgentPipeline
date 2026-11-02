"""План медиа, общий снимок и квитанции: отдельная БД, без сети и моделей."""
import json
import struct
import unittest
from unittest.mock import MagicMock, patch

import test_pipeline as fixture
import results
import telegram as tg
from test_telegram import TelegramTransportTests

db, pl = fixture.db, fixture.pl


class MediaTests(unittest.TestCase):
    def setUp(self):
        fixture.PipelineTests.setUp(self)
        self.photo = fixture.SANDBOX / "image.png"
        self.photo.write_bytes((fixture.SOURCE / "docs/screenshots/board.png").read_bytes())
        self.apk = fixture.SANDBOX / "app.APK"
        self.apk.write_bytes(b"isolated-test-apk")
        self.files = [{"path": str(self.photo), "description": "Доска задач с колонками и карточками."},
                      {"path": str(self.photo), "description": "Второй снимок той же доски."}]
        self.service = tg.Telegram()

    def finish(self, files=None, text="Проверено на заглушках", notify=True):
        db.update_task(self.tid, telegram_notify=notify)
        pl._mcp("finish_task", {"summary": "Готово", "report": "Отчёт", "result_text": text,
                                "result_files": files or []}, self.tid, self.pid)
        row = results.existing(db.get_task(self.tid))
        delivery = db.one("SELECT * FROM telegram_deliveries WHERE task_id=?", (self.tid,))
        return row, json.loads(delivery["payload"]) if delivery else []

    def test_one_and_multiple_photos_compact_with_apk_last(self):
        for count in (1, 2):
            with self.subTest(count=count):
                self.setUp()
                row, parts = self.finish([str(self.apk)] + self.files[:count])
                self.assertEqual(len(parts), 2)
                self.assertEqual(parts[0]["mode"], "photo")
                self.assertEqual(len(parts[0]["files"]), count)
                for i, file in enumerate(self.files[:count], 1):
                    self.assertIn(f"Скрин {i} — " + file["description"], parts[0]["text"])
                self.assertIn("Проверено на заглушках", parts[0]["text"])
                self.assertEqual(parts[-1]["mode"], "document")
                self.assertTrue(parts[-1]["files"][0].endswith("app.APK"))
                self.assertIn("[AP:", parts[0]["text"])

    def test_long_summary_and_description_preserved_with_unicode(self):
        summary = ("Готово 😀\n\n" + "Слова " * 700) * 3 + "КОНЕЦ ИТОГА"
        description = "😀" * 1100 + " КОНЕЦ ПОЯСНЕНИЯ"
        row, parts = self.finish([{**self.files[0], "description": description}], summary)
        clean = [p["text"].rsplit("\n\n[AP:", 1)[0] for p in parts]
        first_image = next(i for i, p in enumerate(parts) if p["files"])
        self.assertIn(summary, "".join(clean[:first_image]))
        caption = "".join(s.split("(продолжение)\n", 1)[-1] for s in clean[first_image:])
        self.assertTrue(caption.endswith("Скрин 1 — " + description))
        for p in parts:
            self.assertLessEqual(tg.units(p["text"]), 1024 if p["files"] else 4096)
        self.assertEqual(json.loads(row["files"])[0]["description"], description)

    def test_no_screenshots_and_legacy_unknown_description(self):
        row, parts = self.finish([str(self.apk)], "Без изображений " * 800)
        self.assertTrue(all(not p["files"] for p in parts[:-1]))
        self.assertTrue(parts[-1]["files"][0].endswith(".APK"))
        self.setUp()
        _, parts = self.finish([str(self.photo)])
        self.assertIn("описание не предоставлено", parts[0]["text"])
        self.assertNotIn("image.png", parts[0]["text"])

    def test_unsupported_media_and_dimensions_use_captioned_documents(self):
        for name, content in (("a.svg", b"<svg/>"), ("bad.png", b"not an image"),
                              ("wide.png", b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 10000, 1))):
            with self.subTest(name=name):
                self.setUp()
                source = fixture.SANDBOX / name
                source.write_bytes(content)
                _, parts = self.finish([{"path": str(source), "description": "Явное пояснение."}])
                self.assertEqual(parts[1]["mode"], "document")
                self.assertIn("Скрин 1 — Явное пояснение.", parts[1]["text"])

    def test_descriptions_survive_without_telegram_late_enable_and_discussion(self):
        import discussions
        row, parts = self.finish(self.files, notify=False)
        self.assertEqual(parts, [])
        self.assertEqual(results.public(row)["files"][0]["description"], self.files[0]["description"])
        captured = discussions.capture(self.pid, {"task_id": self.tid, "result_id": row["id"]})
        self.assertEqual(captured["files"][1]["description"], self.files[1]["description"])
        self.photo.unlink()
        fixture.main.api_task_update(None, {"telegram_notify": True}, {}, self.tid)
        parts = json.loads(db.one("SELECT payload FROM telegram_deliveries WHERE task_id=?", (self.tid,))["payload"])
        self.assertIn(self.files[1]["description"], parts[0]["text"])

    def test_album_confirmed_then_apk_retry_and_duplicate_finish(self):
        self.finish(self.files + [str(self.apk)])
        db.set_setting("telegram_auth", "ready")
        with patch.object(self.service, "_call", side_effect=[{"status": "sent"}, {"status": "error"}]):
            self.service.tick()
        self.assertEqual(tg.delivery(self.tid)["next_part"], 1)
        pl.finish_task(self.tid, "Повтор", "Отчёт")
        self.service.retry(self.tid)
        with patch.object(self.service, "_call", return_value={"status": "sent"}) as call:
            self.service.tick()
            call.assert_called_once()
            self.assertTrue(call.call_args.args[1]["files"][0].endswith(".APK"))

    def test_uncertain_album_no_auto_retry_received_and_resend(self):
        for resolution in ("received", "resend"):
            with self.subTest(resolution=resolution):
                self.setUp()
                self.finish(self.files + [str(self.apk)])
                db.set_setting("telegram_auth", "ready")
                with patch.object(self.service, "_call", return_value={"status": "uncertain"}):
                    self.service.tick()
                self.service.recover()
                with patch.object(self.service, "_call") as call:
                    self.service.tick()
                    call.assert_not_called()
                self.service.retry(self.tid, resolution)
                db.set_setting("telegram_auth", "ready")
                with patch.object(self.service, "_call", return_value={"status": "sent"}) as call:
                    self.service.tick()
                    self.assertEqual(call.call_count, 1 if resolution == "received" else 2)
                self.assertEqual(tg.delivery(self.tid)["state"], "sent")

    def test_album_pre_submit_fallback_persisted_and_resumes_by_document(self):
        self.finish(self.files + [str(self.apk)])
        db.set_setting("telegram_auth", "ready")
        with patch.object(self.service, "_call", side_effect=[{"status": "document_fallback"},
                {"status": "sent"}, {"status": "sent"}, {"status": "uncertain"}]):
            self.service.tick()
        delivery = tg.delivery(self.tid)
        self.assertEqual(delivery["parts"], 4)
        self.assertEqual(delivery["next_part"], 2)
        row = db.one("SELECT payload FROM telegram_deliveries WHERE task_id=?", (self.tid,))
        parts = json.loads(row["payload"])
        self.assertIn("Скрин 2 — Второй снимок", parts[2]["text"])
        self.assertEqual(len({p['text'].split('\n')[-1] for p in parts}), 4)
        self.service.retry(self.tid, "received")
        with patch.object(self.service, "_call", return_value={"status": "sent"}) as call:
            self.service.tick()
            call.assert_called_once()
            self.assertTrue(call.call_args.args[1]["files"][0].endswith(".APK"))


class MediaTransportTests(TelegramTransportTests):
    def test_photo_choice_and_group_upload(self):
        page = MagicMock()
        page.locator.return_value.locator.return_value.count.return_value = 1
        popup = self.helper.upload(page, ["first.png", "second.png"], "photo")
        page.locator(".btn-menu-item").filter.assert_called_with(has_text="Photo or Video")
        page.expect_file_chooser.return_value.__enter__.return_value.value.set_files.assert_called_once_with(["first.png", "second.png"])
        page.wait_for_function.assert_called_once()

    def test_single_media_falls_back_before_submit_and_no_retry_after_submit(self):
        page, popup = MagicMock(), MagicMock()
        before = MagicMock()
        photo = fixture.SOURCE / "docs/screenshots/board.png"
        part = {"text": "Скрин 1 — Доска\n\n[AP:test:1]", "files": [str(photo)], "mode": "photo"}
        with patch.object(self.helper, "upload", side_effect=[RuntimeError(), popup]) as upload, patch.object(self.helper, "wait_sent"):
            self.helper.send(page, part, before)
            self.assertEqual(upload.call_args.args[-1], "document")
            before.assert_called_once()
        before.reset_mock()
        with patch.object(self.helper, "upload", return_value=popup) as upload, patch.object(self.helper, "wait_sent", side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):
                self.helper.send(page, part, before)
            upload.assert_called_once()
            before.assert_called_once()

    def test_group_fallback_is_explicitly_before_submit(self):
        before = MagicMock()
        photo = str(fixture.SOURCE / "docs/screenshots/board.png")
        with patch.object(self.helper, "upload", side_effect=RuntimeError()):
            with self.assertRaises(self.helper.TelegramError) as error:
                self.helper.send(MagicMock(), {"text": "Скрины", "files": [photo, photo], "mode": "photo"}, before)
        self.assertEqual(error.exception.status, "document_fallback")
        before.assert_not_called()

    def test_album_requires_every_item_not_only_caption_marker(self):
        page = MagicMock()
        bubble = page.locator.return_value.filter.return_value.last
        bubble.evaluate.side_effect = [False, False, False, False, False, False, False, True]
        self.helper.wait_sent(page, "[AP:test:1]", 2)
        group_checks = [c for c in bubble.evaluate.call_args_list if len(c.args) == 2]
        self.assertEqual(len(group_checks), 2)
        self.assertEqual(group_checks[-1].args[1], 2)


if __name__ == "__main__":
    unittest.main()
