"""Реальный APK и системный ввод на отдельном эмуляторе, без моделей/Telegram."""
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
    output = Path(__file__).resolve().parents[1] / 'output/playwright/task-45'
    demo = json.loads((output / 'demo.json').read_text(encoding='utf-8'))
    base = 'http://127.0.0.1:' + str(demo['port'])
    pkg = 'space.agentpipeline.android'
    checks = {}
    latest = [None]

    def adb(*argv):
        return subprocess.check_output([args.adb, '-s', args.serial, *argv], timeout=40).decode('utf-8', 'replace').strip()

    def api(path):
        return json.load(urllib.request.urlopen(base + path, timeout=10))

    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Только эмулятор'
    info = api('/api/demo/info')
    assert info['stub_agents']
    adb('reverse', 'tcp:8765', 'tcp:' + str(demo['port']))
    adb('shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
    adb('shell', 'am', 'force-stop', pkg)
    adb('shell', 'am', 'start', '-n', pkg + '/.MainActivity')

    def ui():
        for _ in range(4):
            try:
                adb('shell', 'uiautomator', 'dump', '/sdcard/folders-ui.xml')
                latest[0] = ET.fromstring(adb('shell', 'cat', '/sdcard/folders-ui.xml'))
                return latest[0]
            except (ET.ParseError, subprocess.CalledProcessError):
                time.sleep(.3)
        raise AssertionError('Нет дерева UI')

    def bounds(n):
        return list(map(int, re.findall(r'\d+', n.get('bounds', ''))))

    def find(tree, text, exact=True):
        for n in reversed(list(tree.iter('node'))):
            b = bounds(n)
            if len(b) == 4 and b[2] > b[0] and b[3] > b[1]:
                if any(v == text if exact else text in v for v in (n.get('text', ''), n.get('content-desc', ''))):
                    return n

    def wait(text, exact=True, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            n = find(ui(), text, exact)
            if n is not None:
                return n
        raise AssertionError('Не найдено: ' + text)

    def tap(n):
        l, t, r, b = bounds(n)
        parents = {child: parent for parent in latest[0].iter() for child in parent}
        parent = parents.get(n)
        while parent is not None:
            rect = bounds(parent)
            if parent.get('text') == 'Каталоги сервера' or parent.get('content-desc') == 'Каталоги сервера':
                l, t, r, b = max(l, rect[0]), max(t, rect[1]), min(r, rect[2]), min(b, rect[3])
            parent = parents.get(parent)
        assert r > l and b > t, 'Узел полностью обрезан'
        adb('shell', 'input', 'tap', str((l+r)//2), str((t+b)//2))
        time.sleep(.2)

    def click(text, exact=True):
        tap(wait(text, exact))

    def screenshot(name):
        (output / name).write_bytes(subprocess.check_output([args.adb, '-s', args.serial, 'exec-out', 'screencap', '-p']))

    def enter(n, text):
        tap(n)
        adb('shell', 'input', 'keycombination', '113', '29')
        adb('shell', 'input', 'text', text.replace(' ', '%s').replace('\\', '/'))

    wait('Демо выбора папки')
    time.sleep(1)
    close_chat = find(ui(), '✕')
    if close_chat is not None:
        tap(close_chat)
    click('＋ проект')
    wait('Новый проект')
    fields = [n for n in ui().iter('node') if n.get('class') == 'android.widget.EditText']
    assert len(fields) == 2
    enter(fields[0], 'Android Remote')
    enter(fields[1], demo['sandbox'])
    assert 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')
    screenshot('android-form-keyboard.png')
    adb('shell', 'input', 'keyevent', '4')
    click('Обзор…')
    wait('Папка на ПК с сервером')
    # Рабочая папка — последняя из каталогов тестового sandbox.
    for _ in range(6):
        n = find(ui(), 'Рабочие проекты')
        if n is not None:
            tap(n)
            break
        adb('shell', 'input', 'swipe', '500', '1320', '500', '850', '250')
    wait('Папок: 62')
    screenshot('android-browse.png')
    for _ in range(15):
        n = find(ui(), 'Пустая папка')
        if n is not None:
            tap(n)
            break
        adb('shell', 'input', 'swipe', '500', '1350', '500', '850', '200')
    wait('В этой папке нет вложенных папок')
    screenshot('android-empty.png')
    adb('shell', 'input', 'keyevent', '4')
    wait('Новый проект')
    wait('Android Remote')
    checks['scroll_empty_back_keeps_form'] = True
    click('Обзор…')
    wait('Папка на ПК с сервером')
    click('Диски и корни')
    wait('Диски и корни сервера')
    screenshot('android-roots.png')
    click('Отмена')
    wait('Android Remote')
    checks['roots_cancel_reopen'] = True
    click('Обзор…')
    wait('Папка на ПК с сервером')
    # Ручной ввод ASCII-пути в браузере, с настоящей Android-клавиатурой.
    field = next(n for n in ui().iter('node') if n.get('class') == 'android.widget.EditText')
    enter(field, demo['sandbox'])
    assert 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')
    screenshot('android-picker-keyboard.png')
    assert find(ui(), 'Выбрать папку') is not None, 'Клавиатура скрыла кнопки выбора'
    adb('shell', 'input', 'keyevent', '4')
    click('Перейти')
    wait('Выбрать папку')
    click('Выбрать папку')
    wait('Новый проект')
    click('Создать')
    wait('Android Remote')
    state = api('/api/state')
    assert any(p['name'] == 'Android Remote' and Path(p['path']) == Path(demo['sandbox']) for p in state['projects'])
    checks['keyboard_select_create'] = True

    # Разрыв транспорта с перезапуском Activity закрывает pooled HTTP-сокеты.
    adb('reverse', '--remove', 'tcp:8765')
    adb('shell', 'am', 'force-stop', pkg)
    adb('shell', 'am', 'start', '-n', pkg + '/.MainActivity')
    wait('ERR_CONNECTION_REFUSED', exact=False)
    adb('reverse', 'tcp:8765', 'tcp:' + str(demo['port']))
    click('Обновить страницу')
    wait('Android Remote')
    # Выбор снова доступен после переподключения.
    click('Настройки')
    for _ in range(14):
        n = find(ui(), 'Обзор…')
        if n is not None:
            tap(n)
            break
        adb('shell', 'input', 'swipe', '500', '1500', '500', '600', '200')
    wait('Папка на ПК с сервером')
    click('Отмена')
    checks['reconnect_settings'] = True
    result = {'checks': checks, 'android': adb('shell', 'getprop', 'ro.build.version.release'),
              'apk': '1.1, versionCode 2', 'device': 'emulator only; native input and UIAutomator; no physical phone'}
    (output / 'android-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
