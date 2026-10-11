import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const BASE = '/genesis-architect/';
const dist = join(process.cwd(), 'dist');

// Every built page is a route: the check follows the build, not a hand-kept list.
const routes = [''].concat(
  readdirSync(dist)
    .filter((d) => statSync(join(dist, d)).isDirectory() && existsSync(join(dist, d, 'index.html')))
    .filter((d) => !['_astro', 'pagefind'].includes(d))
    .map((d) => `${d}/`),
);

for (const route of routes) {
  test.describe(`/${route}`, () => {
    test('loads without console errors or failed requests', async ({ page }) => {
      const problems: string[] = [];
      page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text()}`));
      page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
      page.on('response', (r) => r.status() >= 400 && problems.push(`${r.status()} ${r.url()}`));
      const res = await page.goto(BASE + route);
      expect(res?.status()).toBe(200);
      await page.waitForLoadState('networkidle');
      expect(problems).toEqual([]);
    });

    test('has no serious accessibility violations', async ({ page }) => {
      await page.goto(BASE + route);
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
      expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);
    });

    test('does not scroll horizontally', async ({ page }) => {
      await page.goto(BASE + route);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    });
  });
}

test('landing page has one h1 and a canonical link', async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator('h1')).toHaveCount(1);
  await expect(page.locator('link[rel=canonical]')).toHaveAttribute('href', /maioio\.github\.io\/genesis-architect/);
});
