import { expect, test } from '@playwright/test';

/**
 * Installability, asserted here rather than by Lighthouse.
 *
 * Lighthouse 12 removed the PWA category, and with it `installable-manifest`,
 * `service-worker` and `maskable-icon` — the assertions that used to guard this.
 * Dropping them silently would mean nothing checks that the app can still be
 * installed, and a broken manifest fails silently: the browser simply never
 * offers the install prompt, with no error anywhere.
 *
 * The icon fetches matter as much as the manifest fields. A manifest that names
 * an icon which 404s is the single most common cause of an app that builds,
 * deploys, passes every other check, and cannot be installed.
 */

interface ManifestIcon {
  src: string;
  sizes?: string;
  type?: string;
  purpose?: string;
}

interface Manifest {
  name?: string;
  short_name?: string;
  start_url?: string;
  scope?: string;
  display?: string;
  icons?: ManifestIcon[];
  screenshots?: ManifestIcon[];
}

test.describe('installability', () => {
  test('the manifest is linked, complete, and every icon it names resolves', async ({
    page,
    request,
  }) => {
    await page.goto('/');

    const href = await page.locator('link[rel="manifest"]').getAttribute('href');
    expect(href, 'the document should link a manifest').toBeTruthy();

    const response = await request.get(href!);
    expect(response.ok(), `${href} should be fetchable`).toBe(true);
    const manifest = (await response.json()) as Manifest;

    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBeTruthy();
    expect(manifest.scope).toBeTruthy();
    // Anything other than standalone or fullscreen means no install prompt.
    expect(['standalone', 'fullscreen']).toContain(manifest.display);

    const icons = manifest.icons ?? [];
    const sizes = icons.map((i) => i.sizes);
    expect(sizes, 'a 192px icon is required for the launcher').toContain('192x192');
    expect(sizes, 'a 512px icon is required for the splash screen').toContain('512x512');

    // Without a maskable icon, Android crops the square into its adaptive shape
    // and clips the artwork.
    const maskable = icons.filter((i) => i.purpose?.split(/\s+/).includes('maskable'));
    expect(maskable.length, 'at least one maskable icon is required').toBeGreaterThan(0);
    expect(maskable.some((i) => i.sizes === '512x512')).toBe(true);

    // Screenshots drive the richer install dialogue on Android. They are
    // optional to declare and mandatory to serve once declared — these were
    // named by the manifest and returned 404 for the whole of the first build.
    for (const asset of [...icons, ...(manifest.screenshots ?? [])]) {
      const assetResponse = await request.get(asset.src);
      expect(
        assetResponse.ok(),
        `${asset.src} is named by the manifest but does not resolve`,
      ).toBe(true);
      expect(assetResponse.headers()['content-type']).toContain('image/');
    }
  });

  test('a service worker registers and takes control of the page', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, undefined, {
      timeout: 30_000,
    });

    const scope = await page.evaluate(
      async () => (await navigator.serviceWorker.ready).scope,
    );
    // A worker scoped below the root cannot serve navigations to the whole app.
    expect(new URL(scope).pathname).toBe('/');
  });
});
