import { test, expect } from '@playwright/test';

test('workspace pages never expose missing numeric values', async ({ page, request }) => {
  const projects = await (await request.get('/api/projects')).json();
  const project = projects.find((p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''));
  test.skip(!project, 'A completed tender is required for workspace page checks.');
  await page.addInitScript(id => localStorage.setItem('tenderproof_project', id), project.id);
  await page.goto('/');
  for (const pageName of ['Overview', 'Estimate', 'Scenarios', 'Export']) {
    if (pageName !== 'Overview') await page.getByRole('navigation').getByRole('button', { name: pageName, exact: true }).click();
    const text = await page.locator('body').innerText();
    expect(text, `${pageName} contains an invalid numeric value`).not.toMatch(/undefined|NaN/);
    expect(text, `${pageName} contains an incomplete pricing percentage`).not.toMatch(/(?:^|[^\d])% of positions priced/);
  }
});

test('bulk area-rate pricing requires review and a reason before applying', async ({ page, request }) => {
  const projects = await (await request.get('/api/projects')).json();
  const project = projects.find((p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''));
  test.skip(!project, 'A completed tender is required for bulk pricing review.');
  await page.addInitScript(id => localStorage.setItem('tenderproof_project', id), project.id);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: /^Estimate/ }).click();
  const open = page.getByRole('button', { name: /Apply area-rate rule to \d+ rows/ });
  test.skip(!(await open.count()), 'This tender has no eligible rectangular duct rows.');
  const revision = project.revision;
  await open.click();
  const dialog = page.getByRole('dialog', { name: /Apply area-rate rule to \d+ rows/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('tbody tr')).toHaveCount(62);
  const confirm = dialog.getByRole('button', { name: 'Confirm area-rate rule' });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel('Reason for applying this pricing rule').fill('Review the row-level impacts before committing this rule.');
  await expect(confirm).toBeEnabled();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  const unchanged = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(unchanged.revision).toBe(revision);
});

test('real workspace: evidence, edit, reverse, scenarios, export and responsive layout', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const projects = await (await request.get('/api/projects')).json();
  test.skip(!projects.length, 'Import the actual tender before running the integration test.');
  const project = projects.find((p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''));
  test.skip(!project, 'A completed tender is required for reversible workspace checks.');
  await page.addInitScript(id => localStorage.setItem('tenderproof_project', id), project.id);
  const summary = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  test.skip(!summary.coverage.positions_extracted, 'The actual tender must finish extraction first.');
  const positions = await (await request.get(`/api/projects/${project.id}/positions`)).json();
  const editable = positions.items.find(
    (p: { quantity: string | null; cost: { direct_cost_chf: string | null } | null }) =>
      p.quantity !== null && Number(p.cost?.direct_cost_chf) > 0,
  );
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Every number. Backed by evidence.' })).toBeVisible();
  await expect(page.getByText(/INDICATIVE INCLUDED-SCOPE PRICE/)).toBeVisible();
  await page.screenshot({ path: 'test-artifacts/overview-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /^Scope by system/ }).click();
  await page.getByRole('button', { name: 'Category', exact: true }).click();
  await expect(page.getByText('Reconciles to cost baseline')).toBeVisible();
  await page.keyboard.press('Escape');
  await page
    .getByRole('navigation')
    .getByRole('button', { name: /^Estimate/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Inspect. Decide. Defend.' })).toBeVisible();
  if (editable) await page.getByLabel('Search estimate').fill(editable.id);
  await page.locator('.position-link').first().click();
  await expect(page.getByText('EVIDENCE INSPECTOR', { exact: true })).toBeVisible();
  await expect(page.getByText('Unrounded hours used', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Source', exact: true }).click();
  await expect(page.locator('.pdf-sheet')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('.pdf-span').first()).toBeVisible();
  await page.screenshot({ path: 'test-artifacts/evidence-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page
    .getByLabel('Quantity', { exact: false })
    .fill(editable ? String(Number(editable.quantity) + 1) : '2');
  await page
    .getByLabel('Reason for this change')
    .fill('Browser integration verification: explicit quantity override.');
  await page.getByRole('button', { name: 'Save and recalculate' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('saved');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(
    page
      .getByRole('heading', { name: 'Browser integration verification: explicit quantity override.' })
      .first(),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Reverse this change' }).first().click();
  await page
    .getByLabel('Reason for this decision')
    .fill('Restore original quantity after browser verification.');
  await page.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Close evidence inspector' }).click();
  await page.getByRole('button', { name: 'Scenarios', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A range. With a reason.' })).toBeVisible();
  await page.getByText('Scenario assumptions · Commercial context', { exact: true }).click();
  await page.getByLabel('Aggressive margin · %').fill('3.0');
  await page.getByRole('button', { name: 'Recalculate scenarios' }).click();
  await expect(page.getByRole('button', { name: 'Restore saved scenarios' })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  const downloadPromise = page.waitForEvent('download');
  await page
    .locator('.export-card')
    .filter({ hasText: 'Position spreadsheet' })
    .getByRole('button', { name: 'Download' })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.screenshot({ path: 'test-artifacts/overview-tablet.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-artifacts/overview-mobile.png', fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

test('manual evidence recovery, commercial approval and requirement review are reversible', async ({
  page,
  request,
}) => {
  const projects = await (await request.get('/api/projects')).json();
  test.skip(!projects.length, 'Import a real tender first.');
  const project = projects.find((p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''));
  test.skip(!project, 'A completed tender is required for reversible workspace checks.');
  await page.addInitScript(id => localStorage.setItem('tenderproof_project', id), project.id);
  const baseline = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  const runTag = Date.now();
  const adjustmentTitle = `Browser verification access risk ${runTag}`;
  const adjustmentCreateReason = `Browser adjustment creation verification ${runTag}.`;
  const adjustmentApproveReason = `Browser adjustment approval verification ${runTag}.`;
  const requirementReviewReason = `Browser requirement review verification ${runTag}.`;
  const positions = await (await request.get(`/api/projects/${project.id}/positions`)).json();
  const source = positions.items.find(
    (p: {
      source_span_ids: string[];
      quantity: string | null;
      cost: { direct_cost_chf: string | null } | null;
    }) => p.source_span_ids.length && p.quantity !== null && Number(p.cost?.direct_cost_chf) > 0,
  );
  test.skip(!source, 'Wait for extraction to produce a priced source position.');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Every number. Backed by evidence.' })).toBeVisible();
  await page
    .getByRole('navigation')
    .getByRole('button', { name: /^Estimate/ })
    .click();
  await page.getByLabel('Search estimate').fill(source.id);
  await page.locator('.position-link').first().click();
  await page.getByRole('button', { name: 'Source', exact: true }).click();
  await expect(page.locator('.pdf-sheet')).toBeVisible({ timeout: 30000 });
  await page.locator('.pdf-span.source-highlight').first().click();
  await page.getByRole('button', { name: /Create position from selection/ }).click();
  await page
    .getByLabel('Description', { exact: true })
    .fill('Browser verification: intentional independent source-backed scope');
  await page.getByLabel('System', { exact: true }).selectOption(source.system);
  await page.getByLabel('Category', { exact: true }).fill(source.category);
  await page.getByLabel('Quantity', { exact: false }).fill('1');
  await page.getByLabel('Unit', { exact: true }).selectOption(source.unit);
  const manualDecisionReason = `Browser manual-recovery test: intentional split ${Date.now()}.`;
  await page
    .getByLabel('Reason for adding this position')
    .fill(manualDecisionReason);
  await page.getByRole('button', { name: 'Add and calculate' }).click();
  await expect(page.getByText('Possible existing positions', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: /This is an intentional split/ }).check();
  await page.getByRole('button', { name: 'Add and calculate' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await page
    .locator('.history-entry')
    .filter({ hasText: manualDecisionReason })
    .getByRole('button', { name: 'Reverse this change' })
    .click();
  await page
    .getByLabel('Reason for this decision')
    .fill('Reverse manual recovery demonstration after verification.');
  await page.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const afterManual = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(afterManual.coverage.positions_manual).toBe(baseline.coverage.positions_manual);
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await page.getByRole('button', { name: /^Risks/ }).click();
  await page.getByRole('button', { name: 'Add adjustment' }).click();
  await page.getByLabel('Title', { exact: true }).fill(adjustmentTitle);
  await page.getByLabel('Amount · CHF').fill('100');
  await page.getByLabel('Affected scope').fill('browser-test-distinct-scope');
  await page
    .getByLabel('Basis and evidence')
    .fill(
      'Explicit manual demonstration allowance for independent access scope; no existing service overlap.',
    );
  await page
    .getByLabel('Reason', { exact: true })
    .fill(adjustmentCreateReason);
  await page.getByRole('button', { name: 'Save as pending' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const pending = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(pending.totals.cost_baseline_chf).toBe(afterManual.totals.cost_baseline_chf);
  await page.getByRole('button', { name: /^Risks/ }).click();
  await page.getByRole('button', { name: `Approve ${adjustmentTitle}` }).click();
  await page.getByLabel('Reason for this decision').fill(adjustmentApproveReason);
  await page.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const approved = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(Number(approved.totals.cost_baseline_chf)).toBeGreaterThan(Number(pending.totals.cost_baseline_chf));
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  for (const [reason, undoReason] of [
    [adjustmentApproveReason, `Restore pending state after browser test ${runTag}.`],
    [adjustmentCreateReason, `Remove browser test allowance ${runTag}.`],
  ]) {
    await page
      .locator('.history-table tbody tr')
      .filter({ has: page.locator('strong', { hasText: reason }) })
      .getByRole('button', { name: 'Reverse', exact: true })
      .first()
      .click();
    await page.getByLabel('Reason for this decision').fill(undoReason);
    await page.getByRole('button', { name: 'Confirm decision' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  const restored = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  expect(restored.totals.cost_baseline_chf).toBe(afterManual.totals.cost_baseline_chf);
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await page.getByRole('button', { name: /^Requirements/ }).click();
  await page.getByRole('button', { name: 'Mark reviewed', exact: true }).first().click();
  await page.getByLabel('Reason for this decision').fill(requirementReviewReason);
  await page.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  await page
    .locator('.history-table tbody tr')
    .filter({ has: page.locator('strong', { hasText: requirementReviewReason }) })
    .getByRole('button', { name: 'Reverse', exact: true })
    .first()
    .click();
  await page
    .getByLabel('Reason for this decision')
    .fill('Restore requirement review state after verification.');
  await page.getByRole('button', { name: 'Confirm decision' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
