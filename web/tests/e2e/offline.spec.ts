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
 *   1. with the network down the app loads from the service worker
 *   2. it renders the cached digest
 *   3. it displays the correct data age, not just "offline"
 *   4. the user can edit their watchlist while offline
 *   5. that edit flushes when connectivity returns
 */

const WARM_UP_MS = 2_000;

/**
 * Take the network away — from the service worker too.
 *
 * `context.setOffline(true)` on its own is not enough, and quietly produces a
 * test that proves nothing. It stops the *page* from reaching the network, but
 * the worker keeps its own connection: once a worker controls the page, every
 * request is its request, so the app carries on being served fresh from the
 * network while the test believes it is offline. On the Chromium this
 * Playwright ships, `navigator.onLine` is not even flipped, so nothing in the
 * app notices either.
 *
 * Aborting at the route level does reach the worker, which is what makes the
 * cached-document assertions below mean anything. setOffline stays on so the
 * `offline` event still fires, as it would on a real device.
 */
async function cutTheNetwork(context: import('@playwright/test').BrowserContext) {
  await context.route('**/*', (route) => route.abort('internetdisconnected'));
  await context.setOffline(true);
}

async function restoreTheNetwork(context: import('@playwright/test').BrowserContext) {
  await context.unroute('**/*');
  await context.setOffline(false);
}

/**
 * Ask the page whether the network is actually reachable, the same way the app
 * does. Runs inside the browser, so it goes through the service worker exactly
 * as a real request would.
 */
async function reachable(page: import('@playwright/test').Page): Promise<boolean> {
  return page.evaluate(async () => {
    try {
      await fetch('/api/health', { cache: 'no-store' });
      return true;
    } catch {
      return false;
    }
  });
}

/**
 * Sign in through the real magic-link flow.
 *
 * The outbox replays a watchlist edit against /me/watchlist, which is
 * authenticated — so a signed-out flush correctly refuses and the queue would
 * never drain. Testing the flush without a session would be testing nothing.
 *
 * The API returns the link token directly only when IMPACTO_COOKIE_SECURE is
 * false, i.e. local and CI. It is never populated in production.
 */
async function signIn(page: import('@playwright/test').Page): Promise<boolean> {
  const link = await page.request.post('/api/auth/magic-link', {
    data: { email: 'e2e@example.com' },
  });
  if (!link.ok()) return false;
  const { debug_token: token } = (await link.json()) as { debug_token?: string };
  if (!token) return false;

  const verified = await page.request.post('/api/auth/verify', { data: { token } });
  return verified.ok();
}

test.describe('offline-first', () => {
  test('loads, renders cached data with its age, and flushes a queued edit', async ({
    page,
    context,
  }) => {
    // --- warm the caches --------------------------------------------------
    await page.goto('/');
    const authed = await signIn(page);
    test.skip(!authed, 'API not reachable, or not running in dev-auth mode');
    await page.waitForLoadState('networkidle');

    // The service worker must actually take control; asserting on registration
    // alone would pass even if activation failed.
    await page.waitForFunction(
      () => navigator.serviceWorker.controller !== null,
      undefined,
      { timeout: 30_000 },
    );

    // The first document was fetched before the worker existed, so nothing was
    // cached for it. One more online load puts the navigation through the SW —
    // which is what a real second launch does, and what "warm launch" means.
    await page.reload();
    await page.waitForLoadState('networkidle');

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
    await cutTheNetwork(context);
    await page.reload();

    // A page served by the service worker still has a title and a shell.
    await expect(page.locator('main')).toBeVisible();

    // The banner is a client component, so two things have to hold before it can
    // render: the worker must still control the document, and React must have
    // hydrated from cached chunks. Asserting the preconditions separately means
    // a failure says which link broke, instead of only that an element was
    // missing.
    await expect(
      page.evaluate(() => navigator.serviceWorker.controller !== null),
      'the worker should still control the document after an offline reload',
    ).resolves.toBe(true);
    // Deliberately not asserting navigator.onLine: some Chromium builds leave it
    // true throughout, which is exactly why the app probes rather than reads it.
    await expect
      .poll(() => reachable(page), {
        message: 'the network should be unreachable from the page',
        timeout: 10_000,
      })
      .toBe(false);

    // --- 2 & 3. cached data, labelled with its age -----------------------
    // Hydrating offline means parsing every chunk out of Cache Storage, which
    // on a loaded CI runner is slower than the default 5s expect timeout — and
    // slow hydration is not the failure this test exists to catch.
    const banner = page.getByTestId('offline-banner');
    await expect(banner).toBeVisible({ timeout: 30_000 });

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
    await restoreTheNetwork(context);
    await page.reload();
    await page.waitForLoadState('networkidle');

    // The page has to be the one replaying: the outbox lives in its Dexie
    // instance, and startSync() runs the flush on the `online` event.
    await page.evaluate(() => window.dispatchEvent(new Event('online')));

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

  test('labels the data age even when navigator.onLine claims to be online', async ({
    page,
    context,
  }) => {
    // A captive portal, a dead cell connection, or a Chromium that simply keeps
    // reporting true: in all of them the device believes it is online and
    // nothing can be fetched. If the banner trusted the flag, the figures on
    // screen would carry no age at all — which is the one thing this product
    // must never do.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'onLine', { get: () => true, configurable: true });
    });

    await page.goto('/');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, undefined, {
      timeout: 30_000,
    });
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(WARM_UP_MS);

    // Route-level aborts only, deliberately: no setOffline, so nothing tells the
    // browser it is offline and the flag keeps insisting everything is fine.
    await context.route('**/*', (route) => route.abort('internetdisconnected'));
    await page.reload();

    expect(await page.evaluate(() => navigator.onLine), 'the flag should be lying').toBe(true);
    expect(await reachable(page), 'but nothing should be reachable').toBe(false);
    await expect(page.getByTestId('offline-banner')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('data-age')).toBeVisible();
  });

  test('serves the offline fallback for a route that was never cached', async ({
    page,
    context,
  }) => {
    await page.goto('/');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, undefined, {
      timeout: 30_000,
    });
    // Same warm-up: the shell has to have passed through the worker once.
    await page.reload();
    await page.waitForLoadState('networkidle');

    await cutTheNetwork(context);
    const response = await page.goto('/explore/A_ROUTE_NEVER_VISITED', {
      waitUntil: 'domcontentloaded',
    });
    // Either the fallback page or a cached shell — what must not happen is the
    // browser's own network-error page.
    expect(response?.status()).toBeLessThan(500);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
