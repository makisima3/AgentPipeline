"""APK на изолированном эмуляторе через ADB; это не проверка настоящего туннеля Tailscale."""
import argparse
import json
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', default='emulator-5554')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'output/playwright/task-46'
    demo = json.loads((root / 'output/playwright/task-24/demo.json').read_text(encoding='utf-8'))
    base = f"http://127.0.0.1:{demo['port']}"
    pkg = 'space.agentpipeline.android'

    def adb(*argv):
        return subprocess.check_output([args.adb, '-s', args.serial, *argv], timeout=45, stderr=subprocess.PIPE).decode('utf-8', 'replace').strip()

    def api(path, body=None):
        request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(request, timeout=15))

    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Разрешён только эмулятор'
    info = api('/api/demo/info')
    assert info['stub_agents']
    assert api('/api/demo/remote', {'mode': 'serve_configured'})['stub_tailscale']
    adb('reverse', 'tcp:8765', 'tcp:' + str(demo['port']))
    adb('shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
    for key in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
        adb('shell', 'settings', 'put', 'global', key, '0')
    adb('shell', 'input', 'keyevent', '224')
    adb('shell', 'wm', 'dismiss-keyguard')
    adb('shell', 'am', 'force-stop', pkg)
    adb('shell', 'am', 'start', '-n', pkg + '/.MainActivity')

    def ui():
        for _ in range(8):
            try:
                if 'dumped' in adb('shell', 'uiautomator', 'dump', '--compressed', '/sdcard/remote-ui.xml'):
                    return ET.fromstring(adb('shell', 'cat', '/sdcard/remote-ui.xml'))
            except (subprocess.SubprocessError, ET.ParseError):
                pass
            time.sleep(.5)
        raise AssertionError('Не удалось прочитать Android UI')

    def bounds(n):
        return list(map(int, re.findall(r'\d+', n.get('bounds', ''))))

    def find(tree, text, exact=True):
        return next((n for n in tree.iter('node') if len(bounds(n)) == 4 and bounds(n)[2] > bounds(n)[0]
                     and bounds(n)[3] > bounds(n)[1] and any((v == text if exact else text in v)
                     for v in (n.get('text', ''), n.get('content-desc', '')))), None)

    def wait(text, exact=True, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            n = find(ui(), text, exact)
            if n is not None:
                return n
        raise AssertionError('Не найдено: ' + text)

    def tap(n):
        l, t, r, b = bounds(n)
        adb('shell', 'input', 'tap', str((l+r)//2), str((t+b)//2))
        time.sleep(.2)

    def click(text, exact=True):
        tap(wait(text, exact))

    def scroll_to(text, exact=True, down=True):
        previous = None
        for _ in range(30):
            tree = ui()
            signature = ET.tostring(tree)
            if signature == previous:
                down = not down
            previous = signature
            n = find(tree, text, exact)
            if n is not None:
                l, t, r, b = bounds(n)
                web = any(e.get('class') == 'android.webkit.WebView' for e in tree.iter('node'))
                if t >= (420 if web else 180) and b <= (1690 if web else 1850):
                    return n
                move_down = t >= 420
                distance = min(400, max(120, abs((t+b)//2 - 1000)//2))
            else:
                move_down = down
                distance = 500
            adb('shell', 'input', 'swipe', '500', '1100', '500', str(1100-distance if move_down else 1100+distance), '600')
            time.sleep(.3)
        raise AssertionError('Нет после прокрутки: ' + text)

    def screenshot(name):
        (output / name).write_bytes(subprocess.check_output([args.adb, '-s', args.serial, 'exec-out', 'screencap', '-p']))

    def enter(n, value):
        l, t, r, b = bounds(n)
        adb('shell', 'input', 'tap', str(l + 30), str(t + 25))
        adb('shell', 'input', 'keycombination', '113', '29')
        adb('shell', 'input', 'text', value.replace(' ', '%s'))

    checks = {}
    click('Подключение')
    field = next(n for n in ui().iter('node') if n.get('class') == 'android.widget.EditText')
    enter(field, 'http://127.0.0.1:8765')
    assert 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')
    adb('shell', 'input', 'keyevent', '4')
    click('Подключиться')
    wait('Мастерская')
    click('Мастерская')
    checks['native_connection_and_keyboard'] = True
    print('connection passed', flush=True)
    # Новое подключение сохраняет идентификатор этой временной БД.
    click('Настройки')
    tap(scroll_to('Открыть мастер'))
    wait('От задачи до результата')
    tap(scroll_to('Доступ с телефона вне дома', exact=False))
    screenshot('android-wizard.png')
    tap(scroll_to('Проверить Tailscale на ПК'))
    wait('ДЕМО, заглушка Tailscale.', exact=False)
    screenshot('android-address.png')
    checks['shared_wizard_and_cli_stub'] = True
    print('wizard passed', flush=True)
    click('Доска')
    click('Настройки')
    click('Обновить страницу')
    tap(scroll_to('Доступ с телефона вне дома · необязательно'))
    screenshot('android-settings.png')
    checks['settings_reopen'] = True
    print('settings passed', flush=True)

    click('Доска')
    click('Обновить страницу')
    click('＋ Задача')
    wait('Новая задача')
    fields = [n for n in ui().iter('node') if n.get('class') == 'android.widget.EditText' and bounds(n)[2] > 0]
    enter(fields[0], 'Remote Android task')
    adb('shell', 'input', 'keyevent', '4')
    click('Создать')
    assert any(t['title'] == 'Remote Android task' for t in api(f"/api/projects/{info['project_id']}/board")['tasks'])
    checks['create_task'] = True
    click('Вопросы', exact=False)
    questions = api('/api/questions?status=all')
    question = next(q for q in questions if q['task_id'] == info['question_task_id'])
    if question['status'] == 'open':
        click('Интерфейс')
    assert any(q['task_id'] == info['question_task_id'] and q['status'] == 'answered' and q['answer'] == 'Интерфейс'
               for q in api('/api/questions?status=all'))
    checks['answer_question'] = True
    click('Результаты', exact=False)
    before_download = set(adb('shell', 'ls', '/sdcard/Download').splitlines())
    tap(scroll_to('инструкция.txt', exact=False))
    time.sleep(3)
    names = set(adb('shell', 'ls', '/sdcard/Download').splitlines()) - before_download
    assert any('инструкция' in name for name in names), 'DownloadManager не сохранил новый файл'
    # Проверка байтов материала, скачанного именно системным DownloadManager.
    filename = next(line for line in names if line.startswith('инструкция') and line.endswith('.txt'))
    content = adb('shell', 'cat', '/sdcard/Download/' + filename)
    assert 'Демонстрационный материал AgentPipeline' in content
    screenshot('android-download.png')
    checks['result_material_downloadmanager'] = True
    adb('reverse', '--remove', 'tcp:8765')
    adb('shell', 'am', 'force-stop', pkg)
    adb('shell', 'am', 'start', '-n', pkg + '/.MainActivity')
    wait('ERR_CONNECTION_REFUSED', exact=False)
    screenshot('android-offline.png')
    adb('reverse', 'tcp:8765', 'tcp:' + str(demo['port']))
    click('Обновить страницу')
    wait('Результаты', exact=False)
    checks['transport_loss_and_recovery'] = True
    click('Подключение')
    switch = next(n for n in ui().iter('node') if n.get('class') == 'android.widget.Switch')
    if switch.get('checked') != 'true':
        tap(switch)
    tap(scroll_to('Вернуться к задачам'))
    evidence = {'checks': checks, 'android': adb('shell', 'getprop', 'ro.build.version.release'),
                'apk': '1.1 versionCode 2; native code unchanged', 'transport': 'HTTP adb reverse to isolated demo',
                'tailscale': 'CLI stub only; no real tunnel, TLS or mobile network checked'}
    (output / 'android-remote.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=True))


if __name__ == '__main__':
    main()
