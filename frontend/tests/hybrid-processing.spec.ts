import { expect, test } from '@playwright/test';
import { mockWorkspace, savedRun } from './fixtures/mock-workspace';

test('AI opt-in starts the local-first workflow and displays the separate AI review phase', async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.getByRole('button', { name: 'AI configured' }).click();
  const dialog = page.getByRole('dialog');
  const option = dialog.getByRole('checkbox', { name: 'Review unresolved items with AI' });
  await expect(option).not.toBeChecked();
  await expect(dialog).toContainText('First extract the full document locally.');
  await option.check();
  await dialog.getByRole('button', { name: 'Start processing' }).click();
  await expect(dialog).toContainText('Local first, then AI for gaps');
  await expect(dialog).toContainText('12 positions found locally');
  await expect(dialog).toContainText('1/2 review batches completed.');
  await expect(dialog).toContainText('1 positions added · 1 AI refinements for review');
  expect(JSON.parse(state.writes[0].body)).toEqual({ use_ai: true });
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByRole('progressbar', { name: 'AI review progress' })).toHaveAttribute('aria-valuenow', '50');
  await expect(page.locator('.run-banner')).toContainText('Step 2 of 2');
  expect(state.unexpected).toEqual([]);
});

test('run snapshot and current estimate counts are explained without implying local batches use AI', async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.getByRole('button', { name: 'Processing record', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Positions recorded in this run');
  await expect(dialog).toContainText('Current estimate: 13 positions (1 added manually).');
  await expect(dialog).toContainText('AI was not enabled for this run.');
  await dialog.getByText('Processing usage', { exact: true }).click();
  await expect(dialog).toContainText('Local Batches');
  await expect(dialog).not.toContainText('Recorded model usage');
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test('local phase progress does not claim AI has started or that all gaps are resolved', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'local_then_ai', status: 'running',
    stage: 'local extraction · pages 5–8', local_positions_found: null, pages_processed: 8,
    batches_done: 2, completed_at: null }));
  await expect(page.getByRole('progressbar', { name: 'Document extraction progress' })).toHaveAttribute('aria-valuenow', '50');
  await expect(page.locator('.run-banner')).toContainText('Step 1 of 2');
  await page.getByRole('button', { name: 'View progress' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Waiting for local extraction to finish.');
  await expect(dialog).not.toContainText('No unresolved items eligible');
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test('failed AI review reports retained local results without claiming the model succeeded', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'local_then_ai', model: 'test-model',
    ai_batches_total: 3, ai_batches_done: 1, usage: { local_batches: 4, failed_ai_batches: 1, ai_skipped_batches: 2 } }));
  await page.getByRole('button', { name: 'Processing record', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('AI review did not complete successfully. Local results are retained.');
  await expect(dialog).not.toContainText('Model used:');
  await dialog.getByText('Processing usage', { exact: true }).click();
  await expect(dialog).toContainText('AI review batches skipped');
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test('hybrid run with no extraction gaps reports no AI calls and fits a narrow screen', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'local_then_ai', model: 'test-model',
    usage: { local_batches: 4, ai_skipped_batches: 4, successful_ai_batches: 0 } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Processing record', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('No unresolved items eligible for AI review. No AI calls were made.');
  await expect(dialog).toContainText('Configured review model: test-model');
  await expect(dialog).not.toContainText('Model used:');
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBeTruthy();
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test('cached AI review is distinguished from new model calls', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'local_then_ai', model: 'test-model',
    ai_batches_total: 2, ai_batches_done: 2, usage: { local_batches: 4, successful_ai_batches: 0, cached_ai_batches: 2 } }));
  await page.getByRole('button', { name: 'Processing record', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('2/2 review batches completed. 0 successful calls, 2 reused from cache, 0 failed.');
  await expect(dialog).toContainText('Model from cached review: test-model');
  await expect(dialog).not.toContainText('Model used:');
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test('import sends the explicit AI review choice with the uploaded package', async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.getByRole('button', { name: 'Import tender', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('input[type=file]').setInputFiles({ name: 'fixture.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n%%EOF') });
  await dialog.getByRole('checkbox', { name: 'Review unresolved items with AI' }).check();
  await dialog.getByRole('button', { name: 'Import and process' }).click();
  await expect(dialog).toContainText('Processing record');
  const imported = state.writes.find(write => write.path === '/api/projects/import');
  expect(imported?.body).toMatch(/name="use_ai"\r\n\r\ntrue/);
  expect(state.unexpected).toEqual([]);
});

test('explore uses the same local-first AI opt-in', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun(), false);
  await page.getByRole('checkbox', { name: 'Review unresolved items with AI' }).check();
  await page.getByRole('button', { name: 'Explore the Oberglatt tender' }).click();
  await expect(page.getByRole('dialog')).toContainText('Processing record');
  expect(JSON.parse(state.writes[0].body)).toEqual({ use_ai: true });
  expect(state.writes[0].path).toBe('/api/projects/demo');
  expect(state.unexpected).toEqual([]);
});

test('older running servers cannot opt into a different AI workflow', async ({ page }) => {
  const state = await mockWorkspace(page, savedRun({ extraction_mode: 'mixed', status: 'running',
    stage: 'extracting · pages 93–96', completed_at: null }), true, false);
  await expect(page.locator('.run-banner')).toContainText('Extracting');
  await page.getByRole('button', { name: 'AI configured' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('checkbox', { name: 'Review unresolved items with AI' })).toBeDisabled();
  await expect(dialog).toContainText('Restart the app after the current run finishes to enable AI review of unresolved items.');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'View progress' }).click();
  await expect(dialog).toContainText('Local and AI extraction');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Import tender', exact: true }).click();
  await expect(dialog.getByRole('checkbox', { name: 'Review unresolved items with AI' })).toBeDisabled();
  await expect(dialog).toContainText('Restart the app after the current run finishes');
  expect(state.writes).toEqual([]);
  expect(state.unexpected).toEqual([]);
});
