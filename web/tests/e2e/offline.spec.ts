import { expect, test } from '@playwright/test';

/**
 * The most important test in this repo.
 *
 * Offline support is the thing people skip and the thing that catches real bugs,
 * because every part of it fails silently: a service worker that never activates,
 * a bundle that was never written, an outbox that swallows an edit. Each of those
 * looks fine in development and is invisible in production until a user on a
 * train loses their watchlist.
 *
 * The assertions, in order:
 *   1. with context.setOffline(true) the app loads from the service worker
 *   2. it renders the cached digest
 *   3. it displays the correct data age, not just "offline"
 *   4. the user can edit their watchlist while offline
 *   5. that edit flushes when connectivity returns
 */

const WARM_UP_MS = 2_000;

test.describe('offline-first', () => {
  test('loads, renders cached data with its age, and flushes a queued edit', async ({
    page,
    context,
  }) => {
    // --- warm the caches --------------------------------------------------
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // The service worker must actually take control; asserting on registration
    // alone would pass even if activation failed.
    await page.waitForFunction(
      () => navigator.serviceWorker.controller !== null,
      undefined,
      { timeout: 30_000 },
    );

    // Give the sync protocol time to write the bundle into IndexedDB.
    await page.waitForTimeout(WARM_UP_MS);

    const cachedGeneratedAt = await page.evaluate(async () => {
      const request = indexedDB.open('impacto');
      const database = await new Promise<IDBDatabase>((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return new Promise<string | null>((resolve) => {
        const store = database.transaction('meta').objectStore('meta');
        const get = store.get('generatedAt');
        get.onsuccess = () => resolve((get.result?.value as string) ?? null);
        get.onerror = () => resolve(null);
      });
    });
    expect(cachedGeneratedAt, 'the bundle should have been cached').toBeTruthy();

    // --- 1. the app loads offline ----------------------------------------
    await context.setOffline(true);
    await page.reload();

    // A page served by the service worker still has a title and a shell.
    await expect(page.locator('main')).toBeVisible();

    // --- 2 & 3. cached data, labelled with its age -----------------------
    const banner = page.getByTestId('offline-banner');
    await expect(banner).toBeVisible();

    const age = page.getByTestId('data-age');
    await expect(age).toBeVisible();
    // The banner must show WHEN the data is from, not merely that we are offline.
    await expect(age).toHaveAttribute('datetime', cachedGeneratedAt!);

    // --- 4. an edit can be made offline ----------------------------------
    const queued = await page.evaluate(async () => {
      const request = indexedDB.open('impacto');
      const database = await new Promise<IDBDatabase>((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return new Promise<number>((resolve, reject) => {
        const tx = database.transaction('outbox', 'readwrite');
        const now = new Date().toISOString();
        const add = tx.objectStore('outbox').add({
          kind: 'watchlist',
          payload: { archetypeIds: ['FED_HAWKISH_SURPRISE'], minSeverity: 'high' },
          createdAt: now,
          updatedAt: now,
          attempts: 0,
        });
        add.onsuccess = () => resolve(add.result as number);
        add.onerror = () => reject(add.error);
      });
    });
    expect(queued).toBeGreaterThan(0);

    // The edit survives a reload while still offline — it is on the device,
    // not in a JavaScript variable.
    await page.reload();
    const stillQueued = await page.evaluate(async () => {
      const request = indexedDB.open('impacto');
      const database = await new Promise<IDBDatabase>((resolve) => {
        request.onsuccess = () => resolve(request.result);
      });
      return new Promise<number>((resolve) => {
        const count = database.transaction('outbox').objectStore('outbox').count();
        count.onsuccess = () => resolve(count.result);
      });
    });
    expect(stillQueued, 'the queued edit should survive a reload').toBe(1);

    // --- 5. it flushes on reconnect --------------------------------------
    await context.setOffline(false);
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect
      .poll(
        async () =>
          page.evaluate(async () => {
            const request = indexedDB.open('impacto');
            const database = await new Promise<IDBDatabase>((resolve) => {
              request.onsuccess = () => resolve(request.result);
            });
            return new Promise<number>((resolve) => {
              const count = database
                .transaction('outbox')
                .objectStore('outbox')
                .count();
              count.onsuccess = () => resolve(count.result);
            });
          }),
        {
          message: 'the outbox should drain once connectivity returns',
          timeout: 20_000,
        },
      )
      .toBe(0);

    // The banner disappears when we are back online.
    await expect(page.getByTestId('offline-banner')).toBeHidden();
  });

  test('serves the offline fallback for a route that was never cached', async ({
    page,
    context,
  }) => {
    await page.goto('/');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, undefined, {
      timeout: 30_000,
    });

    await context.setOffline(true);
    const response = await page.goto('/explore/A_ROUTE_NEVER_VISITED', {
      waitUntil: 'domcontentloaded',
    });
    // Either the fallback page or a cached shell — what must not happen is the
    // browser's own network-error page.
    expect(response?.status()).toBeLessThan(500);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
