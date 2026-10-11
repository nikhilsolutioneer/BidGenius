import { expect, type Page } from '@playwright/test';
import type { Project, Run, Summary } from '../../src/types';

// Every API request is intercepted. These tests never read or change saved projects.
const recordedAt = '2026-10-11T09:00:00Z';
const document = { id: 'mock-document', filename: 'Example tender.pdf', sha256: 'fixture', page_count: 16 };
export function savedRun(overrides: Partial<Run> = {}): Run {
  return {
    id: 'mock-run', project_id: 'mock-project', status: 'complete', stage: 'complete',
    pages_processed: 16, total_pages: 16, batches_done: 4, batches_total: 4,
    positions_found: 12, local_positions_found: 12, ai_batches_total: 0, ai_batches_done: 0,
    errors: [], extraction_mode: 'local', model: null, prompt_version: 'fixture',
    schema_version: 'fixture', parser_version: 'fixture', started_at: recordedAt,
    updated_at: recordedAt, completed_at: recordedAt, duration_seconds: 1,
    usage: { local_batches: 4, cached_batches: 0 }, cancellation_requested: false,
    ...overrides,
  };
}

export async function mockWorkspace(page: Page, initialRun = savedRun(), hasProject = true, supportsHybrid = true) {
  const state = { run: initialRun, hasProject, writes: [] as { path: string; body: string }[], unexpected: [] as string[] };
  const project = (): Project => ({
    id: 'mock-project', name: 'Mock tender', revision: 1, document, parameters: {},
    latest_run: state.run, created_at: recordedAt, updated_at: recordedAt, estimator: 'Local estimator', bid_status: 'draft',
  });
  const summary = (): Summary => ({
    project_id: 'mock-project', name: 'Mock tender', revision: 1, document, parameters: {},
    totals: { selling_price_chf: '1000', cost_baseline_chf: '800' }, build_up: [], by_system: [], by_category: [],
    coverage: { pages_processed: 16, total_pages: 16, positions_extracted: 12, positions_manual: 1,
      positions_priced: 10, positions_unpriced: 3, provisional_direct_cost_chf: '0', pending_reviews: 3,
      unassigned_blocks: 2, failed_pages: 0 },
    issues: [], requirements: [], adjustments: [], assumptions: [], scope_allocations: [],
    scenarios: { scenarios: [], low_chf: '0', high_chf: '0', assumptions: {}, label: '' },
    latest_run: state.run, review_complete: false, history: [],
  });
  await page.addInitScript(() => {
    localStorage.setItem('bidgenius_session', 'active');
    localStorage.setItem('bidgenius_role', 'Estimator');
    localStorage.setItem('bidgenius_actor', 'Local estimator');
  });
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') {
      state.writes.push({ path, body: request.postData() || '' });
      if (path === '/api/projects/mock-project/runs') {
        state.run = savedRun({ extraction_mode: 'local_then_ai', status: 'running', stage: 'AI review · pages 5–8', completed_at: null,
          model: 'test-model', ai_batches_total: 2, ai_batches_done: 1,
          usage: { local_batches: 4, ai_review_positions: 3, ai_review_source_blocks: 2,
            ai_positions_added: 1, ai_positions_refined: 1, successful_ai_batches: 1, failed_ai_batches: 0 } });
        return route.fulfill({ json: state.run });
      }
      if (['/api/projects/import', '/api/projects/demo'].includes(path)) {
        state.hasProject = true;
        return route.fulfill({ json: { project_id: 'mock-project', run_id: 'mock-run' } });
      }
    } else {
      const responses: Record<string, unknown> = {
        '/api/health': { status: 'ok', version: 'fixture', ai_configured: true, model: 'test-model',
          ...(supportsHybrid ? { processing_modes: ['local', 'local_then_ai'] } : {}) },
        '/api/projects': state.hasProject ? [project()] : [],
        '/api/pinned-demo': null,
        '/api/projects/mock-project': project(),
        '/api/projects/mock-project/summary': summary(),
        '/api/projects/mock-project/positions': { items: [] },
        '/api/projects/mock-project/references': { catalog: [], productivity: [], parameters: {} },
        '/api/runs/mock-run': state.run,
      };
      if (path in responses) return route.fulfill({ json: responses[path] });
    }
    state.unexpected.push(`${request.method()} ${path}`);
    await route.abort();
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Your projects' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: hasProject ? 'Every number. Backed by evidence.' : 'From tender to defensible offer.' })).toBeVisible();
  return state;
}

