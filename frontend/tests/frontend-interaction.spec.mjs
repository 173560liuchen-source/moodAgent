import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('mood_token', 'browser-test-token');
    localStorage.setItem('token', 'browser-test-token');
    localStorage.setItem('mood_user_id', '1');
  });
});

test('未登录首页的登录按钮打开登录弹窗', async ({ browser }) => {
  const context = await browser.newContext();
  const guestPage = await context.newPage();
  await guestPage.goto('/index.html');
  const login = guestPage.locator('.actions .primary');
  await expect(login).toHaveText('登录');
  await expect(login).toHaveAttribute('href', '#login');
  await login.click();
  await expect(guestPage.locator('#auth-modal')).toBeVisible();
  await expect(guestPage.locator('#auth-form')).toBeVisible();
  await expect(guestPage.locator('#auth-nickname-field')).toBeHidden();
  await guestPage.locator('.auth-tab[data-auth-mode="register"]').click();
  await expect(guestPage.locator('#auth-title')).toHaveText('创建账号');
  await expect(guestPage.locator('.auth-nickname')).toBeVisible();
  await context.close();
});

test('未登录不能直接打开用户数据页面', async ({ browser }) => {
  const context = await browser.newContext();
  const guestPage = await context.newPage();
  await guestPage.goto('/app.html');
  await expect(guestPage).toHaveURL(/index\.html\?login=1&return=app\.html/);
  await expect(guestPage.locator('#auth-modal')).toBeVisible();
  await context.close();
});

test('登录态返回首页可直接继续会话', async ({ page }) => {
  await page.goto('/index.html');
  const entry = page.locator('.actions .primary');
  await expect(entry).toHaveText('进入会话');
  await expect(entry).toHaveAttribute('href', 'app.html');
});

test('聊天页可输入消息并呈现流式回复', async ({ page }) => {
  await page.route('http://localhost:8080/agent/gateway/init/stream', async route => {
    await route.fulfill({
      contentType: 'text/event-stream',
      body: 'event: delta\ndata: {"content":"你好，我在。"}\n\n',
    });
  });
  await page.route('http://localhost:8080/agent/gateway/orchestrate/stream', async route => {
    await route.fulfill({
      contentType: 'text/event-stream',
      body: [
        'event: delta\ndata: {"content":"先做一次缓慢呼吸。"}\n\n',
        'event: delta\ndata: {"content":"我会继续陪着你。"}\n\n',
      ].join(''),
    });
  });

  await page.goto('/app.html');
  await expect(page.locator('.welcome-copy')).toContainText('你好，我在。');
  await page.locator('.composer textarea').fill('我今天学习压力很大');
  await page.locator('.composer .send').click();

  await expect(page.locator('.stream-line.user')).toContainText('我今天学习压力很大');
  await expect(page.locator('.stream-line.assistant')).toContainText('先做一次缓慢呼吸。');
  await expect(page.locator('.stream-line.assistant')).toContainText('我会继续陪着你。');
});

test('风险页可查看热线并提交预约', async ({ page }) => {
  let appointmentPayload;
  await page.route('http://127.0.0.1:8080/**', async route => {
    const request = route.request();
    expect(request.headers().authorization).toBe('Bearer browser-test-token');
    const path = new URL(request.url()).pathname;
    if (path === '/help/hotline') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{ title: '校园心理援助热线', phone: '400-123-4567', description: '工作日服务' }]),
      });
      return;
    }
    if (path === '/help/appoint') {
      appointmentPayload = request.postDataJSON();
      await route.fulfill({ contentType: 'text/plain', body: '预约已提交' });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { events: [] } }) });
  });

  await page.goto('/risk-recognition.html?userId=1');
  await page.locator('#open-hotlines').click();
  await expect(page.locator('#hotline-modal')).toBeVisible();
  await expect(page.locator('.dial-hotline')).toHaveAttribute('href', 'tel:4001234567');

  await page.locator('#hotline-modal [data-close-help]').click();
  await page.locator('#open-appointment').click();
  await page.locator('#appointment-name').fill('测试用户');
  await page.locator('#appointment-phone').fill('13800000000');
  await page.locator('#appointment-time').fill('2026-08-16T10:30');
  await page.locator('#appointment-form').press('Enter');

  await expect(page.locator('#appointment-result')).toContainText('预约已提交');
  expect(appointmentPayload).toMatchObject({ userId: 1, name: '测试用户', phone: '13800000000' });
});
