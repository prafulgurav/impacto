import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Zero serious or critical violations on every route.
 *
 * Colour is never the only channel carrying meaning in this product — severity,
 * direction and calibration status all pair their colour with a label — so the
 * contrast and colour rules here are load-bearing rather than box-ticking.
 */
const ROUTES = [
  '/',
  '/explore',
  '/ask',
  '/portfolio',
  '/calibration',
  '/methodology',
  '/compliance',
  '/settings',
  '/more',
  '/offline',
];

for (const route of ROUTES) {
  test(`${route} has no serious or critical accessibility violations`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState('networkidle');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );

    expect(
      blocking,
      blocking
        .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target).join(', ')}`)
        .join('\n'),
    ).toEqual([]);
  });
}

test('both themes are legible', async ({ page }) => {
  for (const theme of ['light', 'dark']) {
    await page.goto('/');
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await page.waitForTimeout(200);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2aa'])
      .include('main')
      .analyze();

    const contrast = results.violations.filter((v) => v.id === 'color-contrast');
    expect(contrast, `${theme}: ${JSON.stringify(contrast)}`).toEqual([]);
  }
});
