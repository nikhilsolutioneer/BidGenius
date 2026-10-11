import { mkdirSync } from 'node:fs';
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('compact page layout, viewport bounds, and serious accessibility checks', async ({ page }) => {
  mkdirSync('test-artifacts/no-scroll', { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Every number. Backed by evidence.' })).toBeVisible();

  for (const destination of ['Overview', 'Analytics', 'Scenarios', 'Export']) {
    await page.getByRole('navigation').getByRole('button', { name: destination, exact: true }).click();
    await page.waitForTimeout(250);
    const layout = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      height: document.documentElement.scrollHeight,
      viewportHeight: innerHeight,
      contentHeight: document.querySelector('.overview-page, .page-content')?.scrollHeight ?? 0,
      contentViewport: document.querySelector('.overview-page, .page-content')?.clientHeight ?? 0,
    }));
    expect(layout.width, `${destination} horizontal overflow`).toBeLessThanOrEqual(layout.viewportWidth + 1);
    expect(layout.height, `${destination} document height`).toBeLessThanOrEqual(layout.viewportHeight + 40);
    expect(layout.contentHeight, `${destination} content area scroll height`).toBeLessThanOrEqual(layout.contentViewport + 2);
    console.log(`${destination} layout`, layout);
    const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    expect(audit.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact || '')),
      `${destination} serious or critical accessibility violations`).toEqual([]);
    await page.screenshot({ path: `test-artifacts/no-scroll/${destination.toLowerCase()}-1440x900.png` });
  }

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByRole('navigation').getByRole('button', { name: 'Overview', exact: true }).click();
  const tablet = await page.evaluate(() => ({ height: document.documentElement.scrollHeight, width: document.documentElement.scrollWidth }));
  expect(tablet.height).toBeLessThanOrEqual(840);
  expect(tablet.width).toBeLessThanOrEqual(1281);
  await page.screenshot({ path: 'test-artifacts/no-scroll/overview-1280x800.png' });

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileWidth = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: innerWidth }));
  expect(mobileWidth.doc).toBeLessThanOrEqual(mobileWidth.view + 1);
  expect(await page.evaluate(() => document.querySelector('.overview-page')?.scrollHeight ?? 0)).toBeLessThan(844 * 1.8);
  await page.screenshot({ path: 'test-artifacts/no-scroll/overview-390x844.png', fullPage: true });
  for (const destination of ['Analytics', 'Scenarios', 'Export']) {
    await page.getByRole('navigation').getByRole('button', { name: destination, exact: true }).click();
    const width = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: innerWidth }));
    expect(width.doc, `${destination} mobile horizontal overflow`).toBeLessThanOrEqual(width.view + 1);
    await page.screenshot({ path: `test-artifacts/no-scroll/${destination.toLowerCase()}-390x844.png`, fullPage: true });
  }
});
