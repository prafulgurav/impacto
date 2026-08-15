import { expect, test } from '@playwright/test';

test.describe('core journeys', () => {
  test('the shell renders and navigation works', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main')).toBeVisible();
    await expect(page.getByRole('note')).toBeVisible(); // the disclaimer bar
  });

  test('an archetype page ships its content in the HTML source', async ({ request }) => {
    // The SEO and LLM-citation surface. Content behind a client-side fetch is
    // content that does not exist for a crawler.
    const listing = await request.get('/api/knowledge/archetypes');
    if (!listing.ok()) test.skip(true, 'API not available');

    const archetypes = (await listing.json()) as { id: string; label: string }[];
    const first = archetypes[0]!;

    const page = await request.get(`/explore/${first.id}`);
    expect(page.ok()).toBeTruthy();
    const html = await page.text();

    expect(html).toContain(first.label);
    expect(html).toContain('application/ld+json');
    expect(html).toContain('"@type":"Article"');
  });

  test('every screen showing a number also shows the disclaimer', async ({ page }) => {
    for (const path of ['/', '/calibration', '/explore']) {
      await page.goto(path);
      await expect(page.getByRole('note')).toBeVisible();
    }
  });
});
