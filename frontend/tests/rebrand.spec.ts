import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

test('rebrand pages, inspector, contrast and responsive screenshots', async ({ page }) => {
  test.skip(process.env.RUN_REBRAND !== '1', 'Rebrand screenshot crawl is opt-in; covered by accessibility/no-scroll smoke tests.');
  const phase = process.env.REBRAND_PHASE || 'after';
  const directory = 'test-artifacts/rebrand';
  mkdirSync(directory, { recursive: true });
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    await route.fulfill({ response: await route.fetch({ url: `http://127.0.0.1:8001${url.pathname}${url.search}` }) });
  });
  const failures: unknown[] = [];
  const audit = async (destination: string, viewport: { width: number; height: number }) => {
    const rendered = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();
    const solid = await page.addStyleTag({ content: '.price-card, .whatif-offer { background: #143f4a !important; }' });
    const flat = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();
    await solid.evaluate(el => el.remove());
    for (const [mode, result] of [['rendered', rendered], ['brightest-gradient', flat]] as const) {
      failures.push(...result.violations.map(v => ({ page: destination, viewport, mode, id: v.id, nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary })) })));
    }
  };
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto('http://127.0.0.1:5173');
    await page.getByRole('navigation').getByRole('button', { name: 'Overview', exact: true }).click();
    await expect(page.getByRole('navigation').getByRole('button', { name: 'Overview', exact: true })).toBeVisible();
    if (phase === 'after') await expect(page.getByRole('link', { name: 'BidGenius AI overview' })).toBeVisible();
    for (const destination of ['Overview', 'Estimate', 'Scenarios', 'Export']) {
      await page.getByRole('navigation').getByRole('button', { name: destination, exact: true }).click();
      if (destination === 'Estimate') await page.locator('.position-link').first().click();
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `${directory}/${phase}-${destination.toLowerCase()}-${viewport.width}x${viewport.height}-full.png`, fullPage: true });
      await page.screenshot({ path: `${directory}/${phase}-${destination.toLowerCase()}-${viewport.width}x${viewport.height}.png` });
      if (phase === 'after') {
        // Axe cannot resolve gradients. Audit against the brightest navy/green
        // blend as well as the actual rendered page, so hero text is not skipped.
        await audit(destination, viewport);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
        if (destination === 'Scenarios' && viewport.width === 1440) {
          await page.locator('.whatif-offer').scrollIntoViewIfNeeded();
          await page.screenshot({ path: `${directory}/after-preview-1440x900.png` });
          await audit('Scenarios summary', viewport);
        }
      }
      if (destination === 'Estimate') await page.getByRole('button', { name: 'Close evidence inspector' }).click();
    }
  }
  writeFileSync(`${directory}/${phase}-contrast.json`, JSON.stringify(failures, null, 2));
  expect(failures).toEqual([]);
});
