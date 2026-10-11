// Read-only screenshot capture for the pitch deck.
// Usage: node pitch/capture.cjs <baseUrl> <projectId> <outDir>
const path = require('path');
const fs = require('fs');
const FE = path.join(__dirname, '..', 'frontend', 'node_modules');
const { chromium } = require(path.join(FE, 'playwright'));

const [base = 'http://127.0.0.1:8000', projectId, outDir = path.join(__dirname, 'shots')] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });

async function session(browser, role, actor) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
  await ctx.addInitScript(([r, a, p]) => {
    localStorage.setItem('bidgenius_session', 'active');
    localStorage.setItem('bidgenius_role', r);
    localStorage.setItem('bidgenius_actor', a);
    if (p) localStorage.setItem('tenderproof_project', p);
    localStorage.setItem('estimate-density', 'compact');
    // Suppress first-visit tours/onboarding so screenshots are clean.
    for (const k of ['bidgenius_tour_done', 'bidgenius_onboarded', 'assistant_onboarded', 'bidgenius_assistant_seen']) localStorage.setItem(k, '1');
  }, [role, actor, projectId]);
  const page = await ctx.newPage();
  return { ctx, page };
}

const nav = (page, name) => page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: true }).click();
const settle = (page, ms = 1500) => page.waitForLoadState('networkidle').catch(() => {}).then(() => page.waitForTimeout(ms));
const shot = async (page, name) => { await page.mouse.move(5, 995); await page.screenshot({ path: path.join(outDir, name + '.png') }); console.log('shot', name); };

async function openFromWorkspace(page, cardIndex) {
  // "My workspace" lists the estimator's projects newest first; open the chosen card.
  const cards = page.locator('button.workspace-project');
  if (await cards.count()) { await cards.nth(cardIndex).click(); await settle(page, 2500); }
}

async function openPosition(page, search, text, rowFilter) {
  await search.fill(text); await settle(page, 1200);
  const row = rowFilter ? page.locator('tbody tr', { hasText: rowFilter }).first() : page.locator('tbody tr').first();
  await row.locator('button[title]').first().click(); await settle(page, 2500);
}

(async () => {
  const browser = await chromium.launch();
  // Login screen
  {
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
    const page = await ctx.newPage();
    await page.goto(base, { waitUntil: 'networkidle' }); await settle(page, 800);
    await shot(page, 'login');
    await ctx.close();
  }
  // Estimator
  {
    const { ctx, page } = await session(browser, 'Estimator', 'Nik');
    await page.goto(base, { waitUntil: 'networkidle' }); await settle(page);
    await shot(page, 'workspace');
    await openFromWorkspace(page, Number(process.env.CARD_INDEX || 0));
    await nav(page, 'Overview'); await settle(page);
    await shot(page, 'overview');
    await nav(page, 'Estimate'); await settle(page);
    const search = page.locator('input[placeholder^="Search positions"]').first();
    await openPosition(page, search, 'Thermische Aussendämmung 60/10', 'p.113');
    const calc = page.getByRole('tab', { name: /Calculation/ }).or(page.getByRole('button', { name: /^Calculation$/ })).first();
    if (await calc.count()) { await calc.click(); await settle(page, 1200); }
    await shot(page, 'inspector-calc');
    const src = page.getByRole('tab', { name: /Source/ }).or(page.getByRole('button', { name: /^Source$/ })).first();
    if (await src.count()) { await src.click(); await settle(page, 3000); }
    await shot(page, 'inspector-source');
    // Scope ambiguity position (controls section, page 110)
    await openPosition(page, search, 'Kanaltemperatur- und Feuchtefühler', 'p.110');
    if (await src.count()) { await src.click(); await settle(page, 3000); }
    await shot(page, 'scope-ambiguity');
    for (const [name, file] of [['Analytics', 'analytics'], ['Scenarios', 'scenarios'], ['Export', 'export']]) {
      const btn = page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name, exact: true });
      if (await btn.count()) { await btn.click(); await settle(page, 2000); await shot(page, file); }
    }
    // Assistant pop-up (opened only, no message sent)
    const launcher = page.getByRole('button', { name: /Ask BidGenius|Assistant/i }).first();
    if (await launcher.count()) { await nav(page, 'Overview'); await settle(page); await launcher.click(); await settle(page, 1200); await shot(page, 'assistant'); }
    await ctx.close();
  }
  // Management
  {
    const { ctx, page } = await session(browser, 'Management', 'Head of Estimating');
    await page.goto(base, { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(12000);
    await shot(page, 'management');
    await ctx.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
