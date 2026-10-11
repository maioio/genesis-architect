// Visual evidence for the release audit: node scripts/screenshots.mjs <base-url> <out-dir>
import { chromium, devices } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const [base = 'http://127.0.0.1:4321/genesis-architect/', out = 'screenshots'] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();

async function shoot(label, ctxOpts, steps) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  for (const [name, fn] of steps) {
    await fn(page);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/${label}-${name}.png` });
  }
  await ctx.close();
}
const section = (id) => async (p) => { await p.goto(base); await p.locator(`#${id}`).scrollIntoViewIfNeeded(); await p.evaluate((i) => document.getElementById(i).scrollIntoView(), id); };

await shoot('desktop', { viewport: { width: 1440, height: 900 } }, [
  ['hero', async (p) => { await p.goto(base); }],
  ['two-path', section('two')],
  ['self-audit', section('self')],
  ['docs', async (p) => { await p.goto(base + 'existing-projects/'); }],
]);
await shoot('mobile', devices['Pixel 7'], [
  ['hero', async (p) => { await p.goto(base); }],
  ['two-path', section('two')],
  ['docs-navigation', async (p) => { await p.goto(base + 'getting-started/'); await p.getByRole('button', { name: /menu/i }).click(); }],
]);
await browser.close();
