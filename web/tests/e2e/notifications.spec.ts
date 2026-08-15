import { expect, test } from '@playwright/test';

/**
 * Permission is asked for contextually or not at all.
 *
 * A denied notification permission is permanent in most browsers. Spending it on
 * someone who has not asked for notifications does not just fail once — it closes
 * the channel for that user forever. So the assertion is not "we show a nice
 * dialog", it is that the browser API is not reachable on load.
 */
test.describe('notification permission', () => {
  test('Notification.requestPermission is never called on page load', async ({ page }) => {
    // Instrument before any app code runs.
    await page.addInitScript(() => {
      (window as unknown as { __permissionCalls: number }).__permissionCalls = 0;
      if (typeof Notification !== 'undefined') {
        const original = Notification.requestPermission.bind(Notification);
        Notification.requestPermission = ((...args: unknown[]) => {
          (window as unknown as { __permissionCalls: number }).__permissionCalls += 1;
          return original(...(args as []));
        }) as typeof Notification.requestPermission;
      }
    });

    for (const path of ['/', '/explore', '/ask', '/settings']) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const calls = await page.evaluate(
        () => (window as unknown as { __permissionCalls: number }).__permissionCalls,
      );
      expect(calls, `permission was requested on ${path}`).toBe(0);
    }
  });

  test('a pre-permission screen explains what will be sent before the browser asks', async ({
    page,
  }) => {
    await page.goto('/settings');
    await page.getByTestId('notify-me').click();

    const dialog = page.getByTestId('pre-permission');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('digest');
    // The frequency has to be stated before the user commits.
    await expect(dialog).toContainText(/notifications a week/i);
    // And what a notification will not contain.
    await expect(dialog).toContainText(/never carries a number/i);
  });
});
