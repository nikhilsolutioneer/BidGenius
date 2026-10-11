import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('square overview shortcuts open full-size details without nested scroll panels', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const shortcuts = page.getByRole('navigation', { name: 'Overview details' });
  await expect(shortcuts.getByRole('button')).toHaveCount(6);
  await expect(page.locator('.overview-middle')).toHaveCount(0);
  await page.screenshot({ path: 'test-artifacts/no-scroll/overview-square-shortcuts.png' });
  for (const title of ['Scope by system', 'Cost build-up', 'Review priorities', 'Requirements', 'Risks']) {
    const opener = shortcuts.getByRole('button', { name: new RegExp(title) });
    await opener.click();
    const dialog = page.getByRole('dialog', { name: title, exact: true });
    await expect(dialog).toBeVisible();
    expect((await dialog.boundingBox())!.height).toBeGreaterThan(700);
    if (title === 'Scope by system') {
      await dialog.getByRole('button', { name: 'Category', exact: true }).click();
      await expect(dialog.locator('.breakdown-item').first()).toBeVisible();
      await page.screenshot({ path: 'test-artifacts/no-scroll/scope-detail-dialog.png' });
      const audit = await new AxeBuilder({ page }).analyze();
      expect(audit.violations.filter(v => ['serious', 'critical'].includes(v.impact || ''))).toEqual([]);
    }
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await shortcuts.getByRole('button', { name: /Scope by system/ }).click();
  const size = await page.locator('.overview-details-dialog').evaluate(el => ({ width: el.clientWidth, scroll: el.scrollWidth }));
  expect(size.scroll).toBeLessThanOrEqual(size.width + 1);
  await page.screenshot({ path: 'test-artifacts/no-scroll/scope-detail-dialog-mobile.png' });
});
