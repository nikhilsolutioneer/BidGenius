import { expect, test } from '@playwright/test';

test('decision charts render, expose tooltips and keep sensitivity read-only', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const projects = await (await request.get('/api/projects')).json();
  const project = projects.find((p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''));
  test.skip(!project, 'A completed tender is required for chart checks.');
  const summary = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  const beforeRevision = summary.revision;
  await page.addInitScript(id => localStorage.setItem('tenderproof_project', id), project.id);
  await page.goto('/');

  const confidence = page.locator('.price-confidence-chart');
  await expect(confidence).toBeVisible();
  const cardSize = await page.locator('.full-scope-card').evaluate(el => ({ height: el.clientHeight, content: el.scrollHeight }));
  expect(cardSize.content, 'Full-scope widget should not clip its content').toBeLessThanOrEqual(cardSize.height + 1);
  await confidence.locator('rect[tabindex="0"]').first().hover();
  await expect(page.getByRole('tooltip')).toContainText('Priced included scope', { timeout: 5000 });
  await confidence.locator('rect[tabindex="0"]').first().focus();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await confidence.locator('xpath=..').getByRole('button', { name: 'View data' }).click();
  await expect(page.locator('.chart-table').first()).toContainText('Priced');
  await expect(page.locator('.chart-table').first()).toContainText('CHF');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.locator('.full-scope-card').getByRole('button', { name: 'Expand chart' }).click();
  await expect(page.getByRole('dialog').locator('.price-confidence-chart')).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();

  await page.getByRole('button', { name: /Cost build-up/ }).click();
  await expect(page.locator('.waterfall-chart')).toBeVisible();
  await expect(page.locator('.waterfall-chart')).toContainText('Final offer price');
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: /Review priorities/ }).click();
  const causeChart = page.locator('.hbar-chart');
  await expect(causeChart).toBeVisible();
  const firstCause = causeChart.locator('.hbar-row').first();
  await firstCause.hover();
  await expect(page.getByRole('tooltip')).toContainText('positions');
  await firstCause.click();
  await expect(page.getByRole('heading', { name: 'Inspect. Decide. Defend.' })).toBeVisible();

  await page.getByRole('navigation').getByRole('button', { name: 'Scenarios', exact: true }).click();
  await page.getByRole('button', { name: /Price sensitivity/ }).click();
  await expect(page.locator('.tornado-chart')).toBeVisible();
  await page.locator('.tornado-row').first().hover();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.curve-chart')).toBeVisible();
  await page.locator('.curve-chart circle[tabindex="0"]').first().focus();
  await expect(page.getByRole('tooltip', { name: /Aggressive|Target|Conservative/ }).last()).toBeVisible();
  await page.screenshot({ path: 'test-artifacts/charts/scenarios-charts-1440x900.png', fullPage: true });

  const sensitivity = await (await request.post(`/api/projects/${project.id}/sensitivity`, { data: { revision: beforeRevision } })).json();
  expect(sensitivity.revision).toBe(beforeRevision);
  const after = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(after.revision).toBe(beforeRevision);
});
