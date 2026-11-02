"""Реальный установленный APK на эмуляторе; только telegram_media_demo.py, без отправки."""
import argparse
import json
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', required=True)
    p.add_argument('--serial', default='emulator-5554')
    args = p.parse_args()
    out = Path(__file__).resolve().parents[1] / 'output/playwright/task-33'
    port = json.loads((out / 'demo.json').read_text(encoding='utf-8'))['port']
    base = f'http://127.0.0.1:{port}'

    def adb(*argv):
        return subprocess.check_output([args.adb, '-s', args.serial, *argv], timeout=40).decode('utf-8', 'replace').strip()

    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Разрешён только эмулятор'
    assert json.load(urllib.request.urlopen(base + '/api/demo/info'))['stub_agents']
    adb('reverse', 'tcp:8765', f'tcp:{port}')
    adb('shell', 'am', 'start', '-n', 'space.agentpipeline.android/.MainActivity')

    def ui():
        for _ in range(4):
            try:
                if 'dumped' in adb('shell', 'uiautomator', 'dump', '/sdcard/media-ui.xml'):
                    return ET.fromstring(adb('shell', 'cat', '/sdcard/media-ui.xml'))
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ET.ParseError):
                pass
        raise AssertionError('Нет дерева UI')

    def bounds(n):
        return list(map(int, re.findall(r'\d+', n.get('bounds', ''))))

    def find(text, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            nodes = list(ui().iter('node'))
            nodes.sort(key=lambda n: 0 if n.get('text') == text or n.get('content-desc') == text else 1)
            for n in nodes:
                b = bounds(n)
                if len(b) == 4 and b[2] > b[0] and b[3] > b[1] and any(text in n.get(k, '') for k in ('text', 'content-desc')):
                    return n
        raise AssertionError('Не найдено: ' + text)

    def click(text):
        l, t, r, b = bounds(find(text))
        adb('shell', 'input', 'tap', str((l+r)//2), str((t+b)//2))

    def screenshot(name):
        (out / name).write_bytes(subprocess.check_output([args.adb, '-s', args.serial, 'exec-out', 'screencap', '-p']))

    def scroll():
        adb('shell', 'input', 'swipe', '800', '1500', '800', '650', '300')

    click('Обновить страницу')
    click('Результаты')
    find('Понятные материалы результата')
    find('Доска проекта: колонки и карточки задач.')
    screenshot('android-result-description.png')
    scroll()
    find('Чат проекта открыт справа от доски.')
    screenshot('android-second-description.png')
    scroll()
    click('Отчёт и материалы')
    find('Понятные материалы результата')
    screenshot('android-result-detail.png')
    adb('shell', 'input', 'keyevent', '4')
    find('Отчёт и материалы')
    # Общий черновик, клавиатура и выбор файла: отправки сообщения нет.
    for _ in range(3):
        try:
            click('Обсудить')
            break
        except AssertionError:
            scroll()
    find('Убрать прикреплённую задачу')
    adb('shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
    editor = next(n for n in ui().iter('node') if n.get('class') == 'android.widget.EditText')
    l, t, r, b = bounds(editor)
    adb('shell', 'input', 'tap', str(l+30), str(t+25))
    adb('shell', 'input', 'text', 'Media%sdraft')
    assert 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')
    screenshot('android-keyboard.png')
    adb('shell', 'input', 'keyevent', '4')
    attachment = out / 'MediaCaptionCheck.txt'
    attachment.write_text('isolated-media-caption-check', encoding='utf-8')
    adb('push', str(attachment), '/sdcard/Download/MediaCaptionCheck.txt')
    click('📎')
    click('Show roots')
    downloads = [n for n in ui().iter('node') if n.get('text') == 'Downloads' and bounds(n) != [0, 0, 0, 0]]
    l, t, r, b = bounds(downloads[-1])
    adb('shell', 'input', 'tap', str((l+r)//2), str((t+b)//2))
    if any(n.get('text') == 'Open from' for n in ui().iter('node')):
        adb('shell', 'input', 'tap', '1000', '600')
    screenshot('android-file-chooser.png')
    click('MediaCaptionCheck.txt')
    find('Media draft')
    find('MediaCaptionCheck.txt')
    adb('reverse', '--remove', 'tcp:8765')
    adb('shell', 'am', 'force-stop', 'space.agentpipeline.android')
    adb('shell', 'am', 'start', '-n', 'space.agentpipeline.android/.MainActivity')
    find('ERR_CONNECTION_REFUSED')
    adb('reverse', 'tcp:8765', f'tcp:{port}')
    click('Обновить страницу')
    find('Media draft')
    find('MediaCaptionCheck.txt')
    find('Убрать прикреплённую задачу')
    check = {'emulator': True, 'android': adb('shell', 'getprop', 'ro.build.version.release'),
             'descriptions': True, 'detailsAndBack': True, 'keyboard': True, 'fileChooser': True,
             'reconnectDraft': True, 'modelsAndRealTelegram': False}
    (out / 'android-check.json').write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(check, ensure_ascii=False))


if __name__ == '__main__':
    main()
