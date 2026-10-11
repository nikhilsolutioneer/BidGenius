import { test, expect } from '@playwright/test';

test('pricing proposal approval, commercial context and saved scenarios remain auditable', async ({
  page,
  request,
}) => {
  const projects = await (await request.get('/api/projects')).json();
  const project = projects.find(
    (p: { latest_run?: { status: string } }) => ['awaiting_review', 'complete'].includes(p.latest_run?.status || ''),
  );
  test.skip(!project, 'A completed real tender is required.');
  const initial = await (await request.get(`/api/projects/${project.id}/summary`)).json();
  const { items } = await (await request.get(`/api/projects/${project.id}/positions`)).json();
  const position = items.find(
    (p: { quantity: string | null; attributes: { pricing_proposals?: { review_state: string }[] } }) =>
      p.quantity != null &&
      p.attributes.pricing_proposals?.some((proposal) => proposal.review_state === 'pending'),
  );
  test.skip(!position, 'A source-linked pricing proposal is required.');
  const reasons = [
    'Browser coverage verification: reviewed catalogue pricing proxy.',
    'Browser coverage verification: installation capacity input.',
    'Browser coverage verification: persisted scenario assumptions.',
  ];
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript((id) => localStorage.setItem('tenderproof_project', id), project.id);
  try {
    await page.goto('/');
    await page.getByRole('navigation').getByRole('button', { name: 'Estimate', exact: true }).click();
    await page.getByLabel('Filter review cause').selectOption('proxy_pending');
    await page.getByLabel('Search estimate').fill(position.id);
    await page.locator('.position-link').first().click();
    await expect(page.getByRole('heading', { name: 'Proposals for estimator approval' })).toBeVisible();
    await page.getByLabel('Proposal decision reason').fill(reasons[0]);
    await page.getByRole('button', { name: 'Approve similar catalogue rate' }).first().click();
    await expect(page.locator('.header-right')).toContainText(`Revision ${initial.revision + 1} saved`);
    const afterApproval = await (await request.get(`/api/projects/${project.id}/positions`)).json();
    const approved = afterApproval.items.find((p: { id: string }) => p.id === position.id);
    expect(
      approved.attributes.pricing_proposals.some(
        (p: { review_state: string }) => p.review_state === 'accepted',
      ),
    ).toBeTruthy();
    expect(approved.technical_equivalence).not.toBe('reviewer_confirmed');
    await page.screenshot({ path: 'test-artifacts/pricing-proxy-approved.png', fullPage: true });

    await page.getByRole('navigation').getByRole('button', { name: 'Scenarios', exact: true }).click();
    await page.getByRole('button', { name: /Scenario assumptions · Commercial context/ }).click();
    await expect(page.getByRole('heading', { name: 'Historical evidence & capacity' })).toBeVisible();
    await expect(page.getByText('Historical evidence & capacity')).toBeVisible();
    await page.getByLabel('Capacity period start').fill('2026-11-01');
    await page.getByLabel('Capacity period end').fill('2026-12-31');
    await page.getByLabel('Available installation hours', { exact: true }).fill('100');
    await page.getByLabel('Already committed hours').fill('80');
    await page.getByLabel('Commercial context change reason').fill(reasons[1]);
    await page.getByRole('button', { name: 'Save commercial context' }).click();
    await expect(page.locator('.header-right')).toContainText(`Revision ${initial.revision + 2} saved`);
    const saved = await (await request.get(`/api/projects/${project.id}/summary`)).json();
    expect(saved.scenarios.scenarios.length).toBeGreaterThan(0);
    const exported = await (
      await request.post(`/api/projects/${project.id}/exports`, {
        data: { revision: saved.revision, format: 'json' },
      })
    ).json();
    const payload = await (await request.get(exported.url)).json();
    expect(payload.summary.scenarios).toEqual(saved.scenarios);
    await page.screenshot({ path: 'test-artifacts/commercial-scenarios-saved.png', fullPage: true });
    expect(errors).toEqual([]);
  } finally {
    for (const reason of [...reasons].reverse()) {
      const current = await (await request.get(`/api/projects/${project.id}/summary`)).json();
      const decision = [...current.history]
        .reverse()
        .find(
          (h: { reason: string; revision: number }) => h.reason === reason && h.revision > initial.revision,
        );
      if (decision) {
        const result = await request.post(`/api/projects/${project.id}/undo/${decision.id}`, {
          data: {
            expected_revision: current.revision,
            reason: `Reverse completed browser coverage verification: ${reason}`,
          },
        });
        expect(result.ok(), await result.text()).toBeTruthy();
      }
    }
  }
});
