import { defineConfig, devices } from '@playwright/test';

/**
 * The offline spec is the most important test in this repo, and it needs a real
 * service worker — so these run against a production build, not `next dev`.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // The GitHub reporter annotates the diff, but writes no report — a failing CI
  // run left nothing to upload and nothing to debug from. Emit the HTML report
  // and keep the trace of anything that failed.
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Some CI images ship a Chromium that does not match the build this
    // Playwright release expects. Point at it explicitly rather than
    // downloading a second copy on every run.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : {},
  },
  projects: [
    {
      name: 'mobile',
      // The target device: a mid-range Android, not a MacBook.
      use: { ...devices['Pixel 7'] },
    },
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'pnpm build && pnpm start',
        url: 'http://127.0.0.1:3000',
        reuseExistingServer: !process.env.CI,
        timeout: 300_000,
      },
});
