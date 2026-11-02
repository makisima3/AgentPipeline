async (page) => {
  const base = new URL(page.url()).origin, output = 'output/playwright/task-46/';
  const assert = (ok, msg) => { if (!ok) throw new Error(msg); };
  const checks = {}, errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const info = await (await page.request.get(base + '/api/demo/info')).json();
  assert(info.stub_agents, 'Нужен remote_demo.py');
  await page.goto(base);
  const state = async () => (await page.request.get(base + '/api/state')).json();
  const initial = (await state()).settings.onboarding_status;
  const mode = async value => page.request.post(base + '/api/demo/remote', {data: {mode: value}});
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  for (const width of [1280, 390]) {
    await page.setViewportSize({width, height: 900});
    if (await page.locator('#chat').isVisible()) await page.locator('#chat').getByRole('button', {name: '✕', exact: true}).click();
    await page.getByRole('button', {name: 'Настройки', exact: true}).click();
    await page.getByRole('button', {name: /^(Открыть мастер|Вернуться к мастеру)$/}).click();
    await page.locator('#onboarding-title').waitFor();
    assert(await page.locator('.onboarding-steps li').count() === 3, 'Добавлен обязательный шаг');
    assert(await page.locator('#remote-guide').getAttribute('open') === null, 'Сценарий должен быть необязательным');
    await page.locator('#view').evaluate(el => el.scrollTop = 0);
    await page.screenshot({path: output + `wizard-overview-${width}.png`});
    await page.locator('#remote-guide summary').click();
    await page.locator('#remote-guide').evaluate(el => el.scrollIntoView({block: 'start'}));
    await page.screenshot({path: output + `wizard-${width}.png`});
    await mode('serve_configured');
    await page.getByRole('button', {name: 'Проверить Tailscale на ПК', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#remote-status')?.dataset.status === 'serve_configured');
    assert(await page.locator('#remote-url').inputValue() === 'https://home.example.ts.net', 'Один адрес');
    await page.getByRole('button', {name: 'Копировать адрес', exact: true}).click();
    assert(await page.evaluate(() => navigator.clipboard.readText()) === 'https://home.example.ts.net', 'Копирование');
    await page.locator('.toast').waitFor({state: 'detached'});
    await page.locator('#remote-status').scrollIntoViewIfNeeded();
    await page.screenshot({path: output + `address-${width}.png`});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Overflow документа');
    assert(await page.locator('#remote-guide').evaluate(el => el.scrollWidth <= el.clientWidth + 1), 'Overflow инструкции');
    await page.getByRole('button', {name: 'Настройки', exact: true}).click();
    await page.locator('#remote-guide summary').click();
    await page.locator('#remote-settings').evaluate(el => el.scrollIntoView({block: 'start'}));
    await page.screenshot({path: output + `settings-${width}.png`});
    for (const value of ['not_installed', 'needs_login', 'needs_serve', 'funnel_detected', 'unavailable', 'serve_configured']) {
      await mode(value);
      await page.getByRole('button', {name: 'Проверить Tailscale на ПК', exact: true}).click();
      await page.waitForFunction(v => document.querySelector('#remote-status')?.dataset.status === v, value);
      assert(await page.locator('#remote-address').isVisible() === (value === 'serve_configured'), 'Выдан небезопасный/старый адрес: ' + value);
      if (value === 'funnel_detected') {
        await page.locator('#remote-status').scrollIntoViewIfNeeded();
        await page.screenshot({path: output + `funnel-${width}.png`});
      }
    }
    assert((await state()).settings.onboarding_status === initial, 'Просмотр сбросил статус мастера');
    checks[`wizard_settings_statuses_copy_responsive_${width}`] = true;
  }
  // Сохранённые completed/skipped остаются после открытия сценария новым устройством.
  for (const status of ['skipped', 'completed']) {
    await page.request.post(base + '/api/settings', {data: {onboarding_status: status}});
    await page.goto(base + '/?setup=remote');
    await page.locator('#remote-guide[open]').waitFor();
    assert((await state()).settings.onboarding_status === status, 'Повторное открытие сбросило статус');
    assert(await page.locator('#welcome').isVisible() === false, 'Повторное предложение мастера');
  }
  // Недоступный HTTP и повторная проверка; обычная доска остаётся доступна.
  await page.route('**/api/remote-access', route => route.abort());
  await page.getByRole('button', {name: 'Проверить Tailscale на ПК', exact: true}).click();
  await page.getByText('Проверка недоступна.', {exact: false}).waitFor();
  assert(await page.locator('#remote-address').isVisible() === false, 'Остался старый адрес');
  await page.unroute('**/api/remote-access');
  await page.getByRole('button', {name: 'Проверить Tailscale на ПК', exact: true}).click();
  await page.waitForFunction(() => document.querySelector('#remote-status')?.dataset.status === 'serve_configured');
  await page.getByRole('button', {name: 'Доска', exact: true}).click();
  await page.getByRole('button', {name: '＋ Задача', exact: true}).waitFor();
  checks.savedStatusAndRetry = true;
  await page.goto(base + '/remote-access.html');
  await page.getByRole('heading', {name: 'Доступ с телефона вне дома', exact: true}).waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Overflow документации');
  assert(errors.length === 0, 'JS: ' + errors.join('; '));
  return checks;
}
