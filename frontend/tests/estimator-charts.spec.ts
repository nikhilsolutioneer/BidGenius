import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('benchmark tables fit and estimator charts offer readable expanded data', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Inspect benchmark allowances' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect((await dialog.boundingBox())!.width).toBeGreaterThan(1200);
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    const overflow = await dialog.locator('.table-scroll').evaluateAll(elements => elements.map(el => el.scrollWidth - el.clientWidth));
    expect(overflow.every(value => value <= 1)).toBeTruthy();
    await page.screenshot({ path: `test-artifacts/no-scroll/benchmark-dialog-${width}.png` });
  }
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('navigation').getByRole('button', { name: 'Analytics', exact: true }).click();
  await expect(page.locator('.donut-chart svg')).toBeVisible();
  await page.getByRole('button', { name: 'Pricing coverage', exact: true }).click();
  await expect(page.locator('.donut-legend')).toContainText('Unpriced');
  await page.getByRole('button', { name: 'Cost mix', exact: true }).click();
  await expect(page.locator('.donut-legend')).toContainText('Material');
  await expect(page.locator('.estimator-svg')).toBeVisible();
  await page.screenshot({ path: 'test-artifacts/no-scroll/analytics-1440x900.png' });
  for (const view of ['cost', 'allowance', 'unpriced']) {
    await page.getByRole('group', { name: 'Estimator chart' }).getByRole('button', { name: { cost: 'Cost by system', allowance: 'Unpriced exposure', unpriced: 'Review workload' }[view], exact: true }).click();
    const panel = page.locator('.analytics-card').last();
    await expect(panel.locator('.estimator-bar-row').first()).toBeVisible();
    await panel.getByRole('button', { name: 'View data', exact: true }).click();
    await expect(dialog.locator('tbody tr').first()).toBeVisible();
    await page.keyboard.press('Escape');
    await panel.getByRole('button', { name: 'Expand chart' }).click();
    await expect(dialog.locator('.estimator-bars')).toBeVisible();
    await page.screenshot({ path: `test-artifacts/no-scroll/estimator-chart-${view}.png` });
    const audit = await new AxeBuilder({ page }).analyze();
    expect(audit.violations.filter(v => ['serious', 'critical'].includes(v.impact || ''))).toEqual([]);
    await page.keyboard.press('Escape');
  }
});
