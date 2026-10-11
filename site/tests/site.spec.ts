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

test('landing page carries Open Graph, Twitter card, icon and description metadata', async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute('content', /social-card\.png$/);
  await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute('content', 'summary_large_image');
  await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /.{40,}/);
  await expect(page.locator('link[rel~="icon"]').first()).toHaveAttribute('href', /favicon/);
});

test('docs pages have a canonical URL, Open Graph image and working sidebar navigation', async ({ page, isMobile }) => {
  await page.goto(BASE + 'getting-started/');
  await expect(page.locator('link[rel=canonical]')).toHaveAttribute('href', 'https://maioio.github.io/genesis-architect/getting-started/');
  await expect(page.locator('meta[property="og:image"]').first()).toHaveAttribute('content', /social-card\.png$/);
  if (isMobile) await page.getByRole('button', { name: /menu/i }).click();
  await page.locator('nav[aria-label="Main"] a[href$="/commands/"]').first().click();
  await expect(page).toHaveURL(/\/genesis-architect\/commands\/$/);
  await expect(page.locator('h1')).toHaveText('Commands');
});

test('code blocks expose a working copy button', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
  await page.goto(BASE + 'getting-started/');
  const block = page.locator('.expressive-code').first();
  await block.hover();
  const button = block.locator('button').first();
  await expect(button).toBeVisible();
  await button.click();
  await expect(block.locator('.feedback')).toHaveCount(1);
});

test('unknown routes return the 404 page under the base path', async ({ page }) => {
  const res = await page.goto(BASE + 'no-such-page/');
  expect(res?.status()).toBe(404);
  await expect(page.locator('h1')).toBeVisible();
});

test('sitemap and robots.txt are served and consistent', async ({ request }) => {
  const robots = await request.get(BASE + 'robots.txt');
  expect(robots.status()).toBe(200);
  expect(await robots.text()).toContain('sitemap-index.xml');
  const index = await request.get(BASE + 'sitemap-index.xml');
  expect(index.status()).toBe(200);
  const sm = await request.get(BASE + 'sitemap-0.xml');
  const xml = await sm.text();
  expect(xml).toContain('https://maioio.github.io/genesis-architect/getting-started/');
  expect((xml.match(/<loc>/g) ?? []).length).toBe(routes.length);
});

test('favicon and social card are served', async ({ request }) => {
  for (const f of ['favicon.svg', 'social-card.png']) {
    expect((await request.get(BASE + f)).status()).toBe(200);
  }
});
