"""Демо пояснений и порядка Telegram, только временная БД; без моделей и отправки."""
import html
import json
import re
from pathlib import Path

import test_pipeline as fixture
import results

db, pl, main = fixture.db, fixture.pl, fixture.main
OUTPUT = fixture.SOURCE / "output/playwright/task-33"


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    db.ex("DELETE FROM projects")
    db.set_setting("onboarding_status", "completed")
    db.set_setting("git_mode", "off")
    pid = db.create_project("Медиа-отчёты", str(fixture.SANDBOX))
    image = fixture.SOURCE / "docs/screenshots/board.png"
    chat = fixture.SOURCE / "docs/screenshots/chat.png"
    apk = fixture.SANDBOX / "Demo.apk"
    apk.write_bytes(b"DEMO ONLY - not an installable APK")
    materials = [{"path": str(image), "description": "Доска проекта: колонки и карточки задач."},
                 {"path": str(chat), "description": "Чат проекта открыт справа от доски."},
                 {"path": str(apk), "description": "Пример места для APK; демо-файл, не устанавливать."}]
    tid = db.create_task(pid, "Понятные материалы результата", telegram_notify=True)
    pl.finish_task(tid, "Пояснения сохранены вместе с изображениями.", "Изолированное демо. Модели и отправка не запускались.",
                   "Готово: два скриншота с пояснениями, затем APK. Это демо порядка, реальной отправки нет.", materials)
    row = results.existing(db.get_task(tid))
    result = results.public(row)
    parts = json.loads(db.one("SELECT payload FROM telegram_deliveries WHERE task_id=?", (tid,))["payload"])
    (OUTPUT / "message-plan.json").write_text(json.dumps(parts, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "demo.json").write_text(json.dumps({"port": 0, "sandbox": str(fixture.SANDBOX)}), encoding="utf-8")

    @main.route("GET", "/api/demo/info")
    def info(h, b, q):
        return {"project_id": pid, "result_id": row["id"], "stub_agents": True}

    @main.route("GET", "/api/demo/order")
    def order(h, b, q):
        return {"parts": parts, "result": result}

    @main.route("GET", "/api/demo/album-check")
    def album_check(h, b, q):
        source = (fixture.SOURCE / 'tools/telegram_web.py').read_text(encoding='utf-8')
        script = re.search(r'complete = bubble.evaluate\("""(.*?)""", count\)', source, re.S).group(1)
        return {"script": script}

    @main.route("GET", "/api/demo/example")
    def example(h, b, q):
        photos = ''.join(f'<figure><img src="{f["url"]}"><figcaption>Скрин {i}</figcaption></figure>'
                         for i, f in enumerate(result['files'][:2], 1))
        caption = html.escape(parts[0]['text'].rsplit('\n\n[AP:', 1)[0])
        page = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Пример порядка Telegram</title><link rel="icon" href="data:,"><style>'
                '*{box-sizing:border-box}body{margin:0;background:#12212d;color:#edf4f8;font:16px/1.5 system-ui}main{max-width:540px;margin:24px auto;padding:16px}'
                'h1{font-size:23px;margin:0}header p{color:#b1c1ce;font-size:14px}article{background:#24475c;padding:16px;border-radius:16px;margin:18px 0}'
                '.album{display:grid;grid-template-columns:1fr 1fr;gap:4px}figure{margin:0;position:relative}img{width:100%;height:190px;object-fit:cover;object-position:top;display:block;border-radius:6px}'
                'figcaption{position:absolute;bottom:5px;left:5px;background:#12212de6;padding:2px 7px;border-radius:5px;font-size:12px}pre{white-space:pre-wrap;font:inherit;overflow-wrap:anywhere}'
                'small{color:#b6cedd}.order{color:#75cfcb;font-size:13px;font-weight:600}.file{display:flex;align-items:center;gap:14px}.icon{font-size:32px}'
                '@media(max-width:420px){main{margin:0 auto;padding:14px}img{height:155px}}</style><main>'
                '<header><h1>Сначала отчёт, потом APK</h1><p>Локальная иллюстрация из нового плана доставки.<br>Это не снимок отправки в Telegram.</p></header>'
                f'<div class="order">1 · Фотоальбом с общей подписью</div><article><div class="album">{photos}</div><pre>{caption}</pre><small>Два изображения в порядке подписи</small></article>'
                '<div class="order">2 · Отдельное сообщение после всех скриншотов</div><article><div class="file"><span class="icon">▣</span><div><b>Demo.apk</b><br><small>APK — демонстрационный файл</small></div></div></article>'
                '<small>При длинном итоге: части полного текста → скрин 1 с пояснением → скрин 2 с пояснением → APK. Ничего не обрезается.</small></main></html>')
        data = page.encode("utf-8")
        h.send_response(200)
        h.send_header("Content-Type", "text/html; charset=utf-8")
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    srv = main.Server(("127.0.0.1", 0), main.Handler)
    (OUTPUT / "demo.json").write_text(json.dumps({"port": srv.server_port, "sandbox": str(fixture.SANDBOX)}), encoding="utf-8")
    print(f"DEMO_PORT={srv.server_port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    run()
