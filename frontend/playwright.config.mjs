import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: /.*\.spec\.mjs/,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5500',
    browserName: 'chromium',
    headless: true,
  },
  webServer: {
    command: 'python -m http.server 5500',
    url: 'http://127.0.0.1:5500/app.html',
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
});
