import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('read-only WCAG audit and final screenshots of the real workspace', async ({
  page,
  request,
}, testInfo) => {
  const projects = await (await request.get('/api/projects')).json();
  test.skip(!projects.length, 'Import the actual tender before checking its workspace.');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Every number. Backed by evidence.' })).toBeVisible();
  const failures: unknown[] = [];
  for (const destination of ['Overview', 'Estimate', 'Scenarios', 'Export']) {
    await page.getByRole('navigation').getByRole('button', { name: destination, exact: true }).click();
    await page.waitForTimeout(300);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    for (const v of results.violations)
      failures.push({
        page: destination,
        id: v.id,
        impact: v.impact,
        description: v.description,
        nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary, html: n.html })),
      });
    await page.screenshot({
      path: `test-artifacts/final-${destination.toLowerCase()}-desktop.png`,
      fullPage: true,
    });
  }
  await page.getByRole('navigation').getByRole('button', { name: 'Estimate', exact: true }).click();
  const positions = await (await request.get(`/api/projects/${projects[0].id}/positions`)).json();
  const chosen = positions.items.find(
    (p: { quantity: string | null; cost: { direct_cost_chf: string | null } | null }) =>
      p.quantity !== null && Number(p.cost?.direct_cost_chf) > 0,
  );
  if (chosen) {
    await page.getByLabel('Search estimate').fill(chosen.id);
    await page.locator('.position-link').first().click();
    for (const tab of ['Calculation', 'Source']) {
      await page.getByRole('button', { name: tab, exact: true }).click();
      if (tab === 'Source') await expect(page.locator('.pdf-sheet')).toBeVisible({ timeout: 30000 });
      const audit = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      for (const v of audit.violations)
        failures.push({
          page: tab,
          id: v.id,
          nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })),
        });
      await page.screenshot({
        path: `test-artifacts/final-${tab === 'Source' ? 'evidence' : 'calculation'}-desktop.png`,
        fullPage: true,
      });
    }
    await page.getByRole('button', { name: 'Edit', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    const editAudit = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    for (const v of editAudit.violations)
      failures.push({
        page: 'edit-dialog',
        id: v.id,
        nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })),
      });
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Close evidence inspector' }).click();
  }
  await page.getByRole('navigation').getByRole('button', { name: 'Overview', exact: true }).click();
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.screenshot({ path: 'test-artifacts/final-overview-tablet.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  for (const v of mobile.violations)
    failures.push({
      page: 'mobile',
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary, html: n.html })),
    });
  await page.screenshot({ path: 'test-artifacts/final-overview-mobile.png', fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBeTruthy();
  await testInfo.attach('accessibility-audit.json', {
    body: JSON.stringify(failures, null, 2),
    contentType: 'application/json',
  });
  expect(failures).toEqual([]);
});

test('welcome and import dialog are keyboard labelled', async ({ page }) => {
  await page.route('**/api/projects', (route) => route.fulfill({ json: [] }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'From tender to defensible offer.' })).toBeVisible();
  await page.screenshot({ path: 'test-artifacts/welcome-desktop.png', fullPage: true });
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.getByRole('button', { name: 'Import package', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Import package', exact: true })).toBeFocused();
});
