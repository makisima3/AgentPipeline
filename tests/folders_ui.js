async (page) => {
  const base = new URL(page.url()).origin;
  const info = await (await page.request.get(base + '/api/demo/info')).json();
  if (!info.stub_agents) throw new Error('Нужен folders_demo.py');
  const output = 'output/playwright/task-45/';
  const checks = {}, errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const wait = async () => { await page.locator('#fp-choose:enabled').waitFor(); };
  const go = async path => {
    await page.locator('#fp-path').fill(path);
    await page.locator('#fp-form button').click();
    await wait();
    await page.waitForFunction(p => document.querySelector('#fp-current').textContent === p, path);
  };
  for (const width of [1280, 390]) {
    await page.setViewportSize({width, height: 844});
    await page.evaluate(() => App.newProject());
    await page.locator('#np-name').fill('Удалённый проект');
    await page.locator('#np-path').fill(info.root);
    await page.locator('#modal').getByRole('button', {name: 'Обзор…', exact: true}).click();
    await wait();
    assert(await page.locator('.folder-entry').count() === 62, 'Показаны файлы или потеряны папки');
    await page.screenshot({path: output + `browse-${width}.png`});
    assert(await page.locator('.folder-picker').evaluate(el => el.scrollWidth <= el.clientWidth), 'Горизонтальный overflow');
    if (width === 390) {
      await page.setViewportSize({width, height: 360});
      await page.locator('.folder-picker.compact').waitFor();
      const button = await page.locator('#fp-choose').boundingBox();
      assert(button.y + button.height <= 360, 'В низком окне кнопки скрыты');
      await page.setViewportSize({width, height: 844});
      await page.locator('.folder-picker:not(.compact)').waitFor();
    }
    await page.locator('#fp-list').evaluate(el => el.scrollTop = el.scrollHeight);
    assert(await page.locator('#fp-list').evaluate(el => el.scrollTop > 0), 'Прокрутка не работает');
    await page.getByRole('button', {name: 'Пустая папка', exact: true}).click();
    await page.getByText('В этой папке нет вложенных папок', {exact: true}).waitFor();
    await page.screenshot({path: output + `empty-${width}.png`});
    await page.locator('#fp-up').click(); await wait();
    await page.locator('#fp-cancel').click();
    assert(await page.locator('#np-path').inputValue() === info.root, 'Отмена изменила путь');
    assert(await page.locator('#np-name').inputValue() === 'Удалённый проект', 'Отмена потеряла имя');
    await page.locator('#modal').getByRole('button', {name: 'Обзор…', exact: true}).click(); await wait();
    await page.locator('#fp-roots').click();
    await page.getByText('Диски и корни сервера', {exact: true}).waitFor();
    assert(await page.locator('#fp-choose').isDisabled(), 'Можно выбрать список корней');
    for (const drive of ['C:\\', 'D:\\']) {
      await page.getByRole('button', {name: drive, exact: true}).click(); await wait();
      await page.locator('#fp-roots').click();
      await page.getByText('Диски и корни сервера', {exact: true}).waitFor();
    }
    await go(info.long);
    await page.screenshot({path: output + `long-${width}.png`});
    await page.locator('#fp-choose').click();
    await page.locator('.folder-picker').waitFor({state: 'detached'});
    assert(await page.locator('#np-path').inputValue() === info.long, 'Длинный путь не подставился');
    await page.getByRole('button', {name: 'Создать', exact: true}).click();
    await page.locator('#np-path').waitFor({state: 'detached'});
    checks[`browse_create_cancel_scroll_drives_long_${width}`] = true;
  }
  await page.evaluate(() => App.newProject());
  await page.locator('#np-name').fill('Сохранить черновик');
  await page.locator('#np-path').fill(info.root);
  await page.locator('#modal').getByRole('button', {name: 'Обзор…', exact: true}).click(); await wait();
  await page.keyboard.press('Escape');
  assert(await page.locator('#np-name').inputValue() === 'Сохранить черновик', 'Escape закрыл обе формы');
  await page.locator('#modal').getByRole('button', {name: 'Обзор…', exact: true}).click(); await wait();
  await page.locator('#fp-path').fill(info.root + '\\Удалено');
  await page.locator('#fp-form button').click();
  await page.getByText('Папка не найдена или удалена. Выберите другую папку', {exact: true}).waitFor();
  assert(await page.locator('#fp-choose').isDisabled(), 'Ошибка допускает подтверждение старой папки');
  await page.screenshot({path: output + 'error-390.png'});
  await go(info.root);
  await page.context().setOffline(true);
  await page.locator('#fp-up').click();
  await page.locator('#fp-retry').waitFor({state: 'visible'});
  await page.context().setOffline(false);
  await page.locator('#fp-retry').click(); await wait();
  await go(info.root);
  // Удаление между просмотром и подтверждением не принимается.
  await page.route('**/api/folders', route => route.fulfill({status: 403, json: {error: 'Нет прав на просмотр этой папки'}}));
  await page.locator('#fp-choose').click();
  await page.getByText('Нет прав на просмотр этой папки', {exact: true}).waitFor();
  assert(await page.locator('#np-path').inputValue() === info.root, 'Неуспешный выбор изменил форму');
  await page.unroute('**/api/folders');
  await page.locator('#fp-retry').click(); await wait();
  // Системная Назад использует тот же мост в установленном APK.
  assert(await page.evaluate(() => App.androidBack()), 'Мост не обработал Назад');
  assert(await page.locator('#np-name').isVisible(), 'Назад потеряла исходную форму');
  await page.getByRole('button', {name: 'Отмена', exact: true}).click();
  checks.errors_offline_retry_escape_back = true;

  await page.evaluate(() => App.setView('settings'));
  if (await page.locator('#chat').isVisible()) await page.locator('#chat .chat-head').getByRole('button', {name: '✕', exact: true}).click();
  await page.locator('#ps-path').fill(info.root);
  await page.locator('button').filter({hasText: /^Обзор…$/}).click(); await wait();
  await go(info.empty);
  await page.locator('#fp-choose').click();
  await page.locator('.folder-picker').waitFor({state: 'detached'});
  assert(await page.locator('#ps-path').inputValue() === info.empty, 'Настройки не получили путь');
  checks.settings = true;
  await page.evaluate(() => App.openOnboarding());
  await page.getByRole('button', {name: 'Добавить проект', exact: true}).click();
  await page.locator('#modal').getByRole('button', {name: 'Обзор…', exact: true}).click();
  await page.getByText('Диски и корни сервера', {exact: true}).waitFor();
  await page.locator('#fp-cancel').click();
  assert(await page.locator('#np-name').isVisible(), 'Отмена в мастере потеряла форму');
  await page.getByRole('button', {name: 'Отмена', exact: true}).click();
  checks.onboarding = true;
  assert(!errors.length, errors.join('\n'));
  return {checks, pageErrors: errors};
}
