// BidGenius AI pitch deck builder.
// Pulls live numbers from the running app + measured evaluation artifacts, then writes pitch/BidGenius_AI_Pitch.pptx.
// Usage: node pitch/build_deck.mjs [baseUrl] [projectId]
//   (run `node pitch/capture.cjs` first for fresh screenshots; crops are produced by pitch/crop.py)
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const PptxGenJS = require('pptxgenjs');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8000';
const SHOTS = path.join(HERE, 'shots');
const CROPS = path.join(SHOTS, 'crops');
const OUT = process.env.OUT || path.join(HERE, 'BidGenius_AI_Pitch.pptx');
// ONLY=1,5,7 builds a subset of slides (for debugging renders).
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(',').map(Number)) : null;
const want = (n) => !ONLY || ONLY.has(n);

// ---------- data ----------
const getJson = async (url) => {
  const r = await fetch(BASE + url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json();
};
const readJson = (rel) => JSON.parse(fs.readFileSync(path.join(ROOT, rel), 'utf8'));

let projectId = process.argv[3];
if (!projectId) projectId = (await getJson('/api/pinned-demo')).project_id;
const s = await getJson(`/api/projects/${projectId}/summary`);
if (s.revision > 1 || (s.history || []).length) {
  console.warn(`WARNING: project ${projectId} is at revision ${s.revision} with ${s.history.length} decisions — reset the demo or pass a clean project id.`);
}
const evalJ = readJson('artifacts/evaluation.json');
const holdout = readJson('artifacts/live-holdout-evaluation.json').holdout;
const validationMd = fs.readFileSync(path.join(ROOT, 'docs/VALIDATION.md'), 'utf8');
const draftSec = Math.round(Number((validationMd.match(/End-to-end[^|]*\|\s*([\d.]+)\s*s/) || [])[1] || evalJ.elapsed_seconds));

const t = s.totals, cov = s.coverage, comp = s.completeness;
const scen = (s.scenarios?.scenarios || []).reduce((m, x) => ({ ...m, [x.scenario]: x }), {});
const D = {
  project: s.name,
  revision: s.revision,
  pages: cov.total_pages,
  pagesDone: cov.pages_processed,
  positions: comp.positions_total,
  priced: cov.positions_priced,
  elsewhere: cov.positions_included_elsewhere ?? 0,
  unpriced: cov.positions_unpriced,
  reviews: cov.pending_reviews,
  quotes: cov.supplier_quotes_required,
  ambiguity: cov.unresolved_by_cause?.scope_ambiguity ?? 0,
  pctValue: Number(comp.pct_value_priced),
  offer: Number(t.selling_price_chf),
  baseline: Number(t.cost_baseline_chf),
  margin: Number(s.parameters.commercial.target_margin_pct),
  allowLow: Number(comp.allowance_low_chf),
  allowHigh: Number(comp.allowance_high_chf),
  fullLow: Number(s.likely_total_low),
  fullHigh: Number(s.likely_total_high),
  aggressive: Number(scen.Aggressive?.bid_price_chf),
  target: Number(scen.Target?.bid_price_chf),
  conservative: Number(scen.Conservative?.bid_price_chf),
  verified: evalJ.verified_examples.complete_row,
  holdout,
  draftSec,
  parseSec: Math.round(evalJ.elapsed_seconds),
};

// ---------- formatting ----------
const grp = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '’');
const chf = (n) => `CHF ${grp(n)}`;
const chfM = (n) => `CHF ${(Math.round(n / 1e4) / 100).toFixed(2)}M`;
const chfK = (n) => `CHF ${Math.round(n / 1000)}k`;

// ---------- crops ----------
const py = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
const dims = JSON.parse(execFileSync(py, ['-I', path.join(HERE, 'crop.py'), SHOTS], { encoding: 'utf8' }));

// ---------- design tokens ----------
const NAVY = '00243A', NAVY2 = '0A3550', GREEN = '70BC95', INK = '277350', TINT = 'E8F5EE';
const MUTED = '5A6B78', BORDER = 'DCE4E2', BG = 'F4F7F6', WHITE = 'FFFFFF', SOFT = 'B9CBD4';
const FONT = 'Segoe UI', FONT_B = 'Segoe UI Semibold';

const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_WIDE'; // 13.333 x 7.5 in
pptx.author = 'Team BidGenius';
pptx.title = 'BidGenius AI — From tender to priced offer';
const W = 13.333, H = 7.5;
let slideNo = 0;

// No drop shadows: several shadowed shapes on one slide crash LibreOffice's PDF export.
const shadow = undefined;

function waves(slide, cx = 11.0, cy = 3.9) {
  [3.4, 2.5, 1.6].forEach((r, i) => slide.addShape(pptx.ShapeType.ellipse, {
    x: cx - r, y: cy - r, w: r * 2, h: r * 2,
    fill: { color: NAVY, transparency: 100 }, line: { color: GREEN, width: 1.25, transparency: 55 + i * 10 },
  }));
  slide.addShape(pptx.ShapeType.ellipse, { x: cx - 1.75, y: cy - 2.65, w: 0.14, h: 0.14, fill: { color: GREEN }, line: { color: GREEN } });
  slide.addShape(pptx.ShapeType.ellipse, { x: cx + 1.9, y: cy + 1.9, w: 0.12, h: 0.12, fill: { color: GREEN }, line: { color: GREEN } });
}

function navySlide() {
  const slide = pptx.addSlide();
  slideNo += 1;
  slide.background = { color: NAVY };
  return slide;
}

function contentSlide(tag, title) {
  const slide = pptx.addSlide();
  slideNo += 1;
  slide.background = { color: WHITE };
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.12, h: H, fill: { color: NAVY }, line: { color: NAVY } });
  slide.addText(tag, { x: 0.7, y: 0.42, w: 9, h: 0.32, fontFace: FONT_B, fontSize: 12, color: INK, charSpacing: 3, margin: 0 });
  slide.addText(title, { x: 0.7, y: 0.78, w: 11.9, h: 0.8, fontFace: FONT_B, fontSize: 32, color: NAVY, margin: 0 });
  slide.addText([{ text: 'BidGenius', options: { bold: true } }, { text: ' AI  ·  Equans case  ·  ' + slideNo }], {
    x: 0.7, y: H - 0.45, w: 6, h: 0.25, fontFace: FONT, fontSize: 10, color: MUTED, margin: 0,
  });
  return slide;
}

// Image with a thin frame; width or height given, other side from crop aspect.
function shot(slide, name, { x, y, w, h }) {
  const [pw, ph] = dims[name];
  if (w && !h) h = (w * ph) / pw;
  if (h && !w) w = (h * pw) / ph;
  slide.addShape(pptx.ShapeType.roundRect, { x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08, rectRadius: 0.06, fill: { color: WHITE }, line: { color: BORDER, width: 1 }, shadow });
  slide.addImage({ path: path.join(CROPS, name + '.png'), x, y, w, h });
  return { x, y, w, h, px: (rx) => x + (rx / pw) * w, py: (ry) => y + (ry / ph) * h };
}

function badge(slide, n, x, y, d = 0.38) {
  slide.addShape(pptx.ShapeType.ellipse, { x: x - d / 2, y: y - d / 2, w: d, h: d, fill: { color: INK }, line: { color: WHITE, width: 1.5 } });
  slide.addText(String(n), { x: x - d / 2, y: y - d / 2, w: d, h: d, fontFace: FONT_B, fontSize: 13, color: WHITE, align: 'center', valign: 'middle', margin: 0 });
}

function band(slide, text, y = 6.2) {
  slide.addShape(pptx.ShapeType.roundRect, { x: 0.7, y, w: W - 1.4, h: 0.62, rectRadius: 0.08, fill: { color: TINT }, line: { color: TINT } });
  slide.addText(text, { x: 0.95, y, w: W - 1.9, h: 0.62, fontFace: FONT_B, fontSize: 16, color: NAVY, valign: 'middle', margin: 0 });
}

// ============ 1. Title ============
if (want(1)) {
  const sl = navySlide();
  waves(sl);
  sl.addText('SPRINTD ZÜRICH  ·  EQUANS CASE  ·  FROM TENDER TO PRICED OFFER', { x: 0.8, y: 0.8, w: 9, h: 0.35, fontFace: FONT_B, fontSize: 12, color: GREEN, charSpacing: 3, margin: 0 });
  sl.addText([{ text: 'BidGenius ', options: { color: WHITE } }, { text: 'AI', options: { color: GREEN } }], { x: 0.8, y: 2.0, w: 8, h: 1.3, fontFace: FONT_B, fontSize: 72, margin: 0 });
  sl.addText('Every number. Backed by evidence.', { x: 0.8, y: 3.4, w: 8, h: 0.7, fontFace: FONT_B, fontSize: 30, color: WHITE, margin: 0 });
  sl.addText(`From a ${D.pages}-page tender to a price an estimator can defend — line by line.`, { x: 0.8, y: 4.2, w: 7.2, h: 0.9, fontFace: FONT, fontSize: 18, color: SOFT, margin: 0 });
  sl.addText('Team BidGenius  ·  October 2026', { x: 0.8, y: 6.6, w: 6, h: 0.3, fontFace: FONT, fontSize: 12, color: SOFT, margin: 0 });
  sl.addNotes(`[0:00–0:15] Speaker faces the jury, driver has the app ready on My workspace.
"BidGenius turns a ${D.pages}-page tender into a price you can defend, line by line — and tells you exactly what it doesn't know yet."`);
}

// ============ 2. Problem ============
if (want(2)) {
  const sl = contentSlide('THE PROBLEM', 'One tender. 202 pages. One shot at the price.');
  const cols = [
    [String(D.pages), 'pages of German tender text', 'Schulhaus Oberglatt · BKP 244 ventilation'],
    [grp(D.positions), 'line items to quantify, match and price', 'today: read and priced by hand'],
    ['0', 'price negotiations after submission', '„1.17 Preisverhandlungen ausgeschlossen.“ — tender p. 9'],
  ];
  cols.forEach(([big, label, sub], i) => {
    const x = 0.7 + i * 4.05;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 1.95, w: 3.8, h: 3.7, rectRadius: 0.1, fill: { color: BG }, line: { color: BORDER } });
    sl.addText(big, { x: x + 0.35, y: 2.2, w: 3.2, h: 1.4, fontFace: FONT_B, fontSize: 80, color: i === 2 ? INK : NAVY, margin: 0 });
    sl.addText(label, { x: x + 0.35, y: 3.65, w: 3.2, h: 0.9, fontFace: FONT_B, fontSize: 19, color: NAVY, margin: 0, valign: 'top' });
    sl.addText(sub, { x: x + 0.35, y: 4.65, w: 3.2, h: 0.8, fontFace: FONT, fontSize: 13, color: MUTED, italic: i === 2, margin: 0, valign: 'top' });
  });
  band(sl, 'In a low-margin business, one missed line is the margin.');
  sl.addNotes(`[0:15–0:35] "This is the Oberglatt school ventilation tender: ${D.pages} pages of German, ${D.positions} line items. Page 9 says it plainly: no price negotiations. The first price is final. Today an estimator builds that price by hand — and one missed line can be the whole margin."`);
}

// ============ 3. Our answer ============
if (want(3)) {
  const sl = contentSlide('OUR ANSWER', 'Read. Match. Price. Defend.');
  const cards = [
    ['Read', `All ${D.pagesDone}/${D.pages} pages parsed on a laptop — a reviewable, priced draft in ${D.draftSec} seconds.`, 'FEASIBILITY'],
    ['Match', 'Every line linked to your catalogue and labour rules, with a visible confidence band.', 'TRACEABILITY'],
    ['Price', 'Exact CHF maths: quantity × net price × waste, plus hours × site factors × rate.', 'IMPACT'],
    ['Defend', 'Every number opens its PDF page. Every change needs a reason and creates a revision.', 'TRACEABILITY'],
  ];
  cards.forEach(([head, body, tag], i) => {
    const x = 0.7 + i * 3.05;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 1.95, w: 2.85, h: 3.55, rectRadius: 0.1, fill: { color: WHITE }, line: { color: BORDER }, shadow });
    badge(sl, i + 1, x + 0.55, 2.55, 0.5);
    sl.addText(head, { x: x + 0.3, y: 3.0, w: 2.3, h: 0.55, fontFace: FONT_B, fontSize: 24, color: NAVY, margin: 0 });
    sl.addText(body, { x: x + 0.3, y: 3.6, w: 2.3, h: 1.4, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0, valign: 'top' });
    sl.addText(tag, { x: x + 0.3, y: 5.05, w: 2.3, h: 0.3, fontFace: FONT_B, fontSize: 10, color: INK, charSpacing: 2, margin: 0 });
    if (i < 3) sl.addText('›', { x: x + 2.83, y: 3.3, w: 0.24, h: 0.6, fontFace: FONT_B, fontSize: 30, color: GREEN, align: 'center', margin: 0 });
  });
  band(sl, 'AI proposes. Deterministic maths prices. The estimator decides — every number.');
  sl.addNotes(`[0:35–0:50] "BidGenius does four things: it reads the whole tender, matches every line to your catalogue and labour rules, prices it with exact maths — the AI never sets a price — and lets the estimator defend every number. Let me show you." → SWITCH TO DEMO`);
}

// ============ 4. Demo divider ============
if (want(4)) {
  const sl = navySlide();
  waves(sl, 11.4, 3.75);
  sl.addText('LIVE DEMO', { x: 0.8, y: 1.0, w: 6, h: 0.35, fontFace: FONT_B, fontSize: 12, color: GREEN, charSpacing: 3, margin: 0 });
  sl.addText('Watch for three moments', { x: 0.8, y: 1.45, w: 9, h: 0.9, fontFace: FONT_B, fontSize: 40, color: WHITE, margin: 0 });
  const rows = [
    ['The honest number', 'what is priced and proven — and what is not, yet'],
    ['The page that says „Nicht Bestandteil dieser Submission“', 'and why BidGenius stops instead of pricing it'],
    ['The assumption that moves the price most', 'previewed live, applied with a reason, reversible'],
  ];
  rows.forEach(([h, sub], i) => {
    const y = 2.85 + i * 1.15;
    sl.addShape(pptx.ShapeType.ellipse, { x: 0.8, y, w: 0.6, h: 0.6, fill: { color: GREEN }, line: { color: GREEN } });
    sl.addText(String(i + 1), { x: 0.8, y, w: 0.6, h: 0.6, fontFace: FONT_B, fontSize: 20, color: NAVY, align: 'center', valign: 'middle', margin: 0 });
    sl.addText(h, { x: 1.65, y: y - 0.05, w: 8.2, h: 0.45, fontFace: FONT_B, fontSize: 22, color: WHITE, margin: 0 });
    sl.addText(sub, { x: 1.65, y: y + 0.4, w: 8.2, h: 0.35, fontFace: FONT, fontSize: 15, color: SOFT, margin: 0 });
  });
  sl.addNotes(`Optional — show for 3 seconds while the driver switches windows, or skip straight to the app.
Demo path (≈3:20): My workspace → open draft → Overview honest number → Estimate: LA02 p.113 insulation (Calculation, then Source) → LA02 p.110 scope ambiguity (choose "Install only" with a reason) → Scenarios: sensitivity + slider + apply with reason → Export package.`);
}

// ============ 5. Impact ============
if (want(5)) {
  const sl = contentSlide('IMPACT & RELEVANCE  ·  30%', 'A price an estimator would trust');
  sl.addText(chf(D.offer), { x: 0.7, y: 1.85, w: 5.2, h: 0.85, fontFace: FONT_B, fontSize: 44, color: NAVY, margin: 0 });
  sl.addText(`included-scope offer · ${D.pctValue.toFixed(1)}% of estimated value priced · ${D.margin}% margin · before VAT`, { x: 0.7, y: 2.7, w: 4.9, h: 0.6, fontFace: FONT, fontSize: 13, color: MUTED, margin: 0, valign: 'top' });
  // price-confidence bar
  const bx = 0.7, by = 3.6, bw = 4.9, bh = 0.42, max = D.fullHigh;
  const sx = (v) => bx + (v / max) * bw;
  sl.addShape(pptx.ShapeType.rect, { x: bx, y: by, w: sx(D.offer) - bx, h: bh, fill: { color: INK }, line: { color: INK } });
  sl.addShape(pptx.ShapeType.rect, { x: sx(D.offer) + 0.03, y: by, w: sx(D.fullLow) - sx(D.offer) - 0.03, h: bh, fill: { color: GREEN, transparency: 35 }, line: { color: GREEN, transparency: 35 } });
  sl.addShape(pptx.ShapeType.rect, { x: sx(D.fullLow) + 0.03, y: by, w: sx(D.fullHigh) - sx(D.fullLow) - 0.03, h: bh, fill: { color: TINT }, line: { color: GREEN, width: 1.25, dashType: 'dash' } });
  sl.addText('Priced & proven', { x: bx, y: by + 0.5, w: 2.4, h: 0.3, fontFace: FONT_B, fontSize: 12, color: INK, margin: 0 });
  sl.addText(`Full scope ${chfM(D.fullLow)}–${chfM(D.fullHigh)}`, { x: bx + 2.0, y: by + 0.5, w: 2.9, h: 0.3, fontFace: FONT_B, fontSize: 12, color: NAVY, align: 'right', margin: 0 });
  sl.addText([
    { text: `Unpriced scope: ${chfK(D.allowLow)}–${chfK(D.allowHigh)} `, options: { bold: true, color: NAVY } },
    { text: 'benchmark range — shown, never hidden inside the bid.', options: { color: MUTED } },
  ], { x: 0.7, y: 4.55, w: 4.9, h: 0.7, fontFace: FONT, fontSize: 14, margin: 0, valign: 'top' });
  sl.addText([
    { text: `${D.reviews} review items `, options: { bold: true, color: NAVY } },
    { text: `ranked by cause, ${D.quotes} supplier quote requests drafted.`, options: { color: MUTED } },
  ], { x: 0.7, y: 5.25, w: 4.9, h: 0.7, fontFace: FONT, fontSize: 14, margin: 0, valign: 'top' });
  const hero = shot(sl, 'overview_hero', { x: 6.1, y: 1.95, w: 6.55 });
  const queue = shot(sl, 'overview_queue', { x: 6.1, y: hero.y + hero.h + 0.3, w: 6.55 });
  sl.addText('Most tools hand you a number. BidGenius hands you a number and its gaps.', { x: 6.1, y: queue.y + queue.h + 0.35, w: 6.55, h: 0.8, fontFace: FONT_B, fontSize: 17, color: NAVY, margin: 0, valign: 'top' });
  sl.addNotes(`Backup / handout for the "honest number" demo beat.
"${chf(D.offer)} is priced and proven — ${D.pctValue.toFixed(0)}% of the value. The rest is not hidden: a benchmark range of ${chfK(D.allowLow)} to ${chfK(D.allowHigh)}, so the realistic full scope is ${chfM(D.fullLow)} to ${chfM(D.fullHigh)}. And here is the to-do list, ranked by cause."`);
}

// ============ 6. Traceability ============
if (want(6)) {
  const sl = contentSlide('TRACEABILITY  ·  20%', 'Every number links back to the tender');
  const im = shot(sl, 'inspector_calc', { x: 0.8, y: 1.75, h: 4.25 });
  // Callouts sit in the left margin, with a short leader to the row they explain.
  [[1, 573], [2, 797]].forEach(([n, ry]) => {
    sl.addShape(pptx.ShapeType.line, { x: im.x - 0.3, y: im.py(ry), w: 0.42, h: 0, line: { color: INK, width: 1.5 } });
    badge(sl, n, im.x - 0.36, im.py(ry));
  });
  const rows = [
    ['Quantity → tender page', '310 m² read from PDF page 113. One click opens the page with the source line highlighted.'],
    ['Price → your catalogue', 'P-INS-002 from catalog.csv, match band “Strong”. A pricing reference — technical equivalence stays a separate decision.'],
    ['Labour → your productivity rules', 'Base hours × site factors × role rate, unrounded hours, written out as a formula with its source rows.'],
  ];
  rows.forEach(([h, body], i) => {
    const y = 1.85 + i * 1.38;
    badge(sl, i + 1, 5.05, y + 0.2, 0.46);
    sl.addText(h, { x: 5.5, y, w: 7.1, h: 0.42, fontFace: FONT_B, fontSize: 20, color: NAVY, margin: 0 });
    sl.addText(body, { x: 5.5, y: y + 0.45, w: 7.1, h: 0.8, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0, valign: 'top' });
  });
  band(sl, `The same for all ${D.positions} positions — and every change records owner, reason and CHF effect, reversible.`);
  sl.addNotes(`Backup / handout for the inspector demo beat.
"Take any line. 310 square metres of insulation: quantity from page 113, net price from your catalogue, labour from your productivity sheet — and the original page, highlighted. Nothing is a black box."`);
}

// ============ 7. It knows when to stop ============
if (want(7)) {
  const sl = contentSlide('TRACEABILITY  ·  IMPACT', 'It knows when to stop');
  const im = shot(sl, 'scope_pdf', { x: 0.8, y: 1.75, h: 4.25 });
  sl.addShape(pptx.ShapeType.roundRect, { x: im.px(105), y: im.py(500), w: im.px(470) - im.px(105), h: im.py(552) - im.py(500), rectRadius: 0.04, fill: { color: GREEN, transparency: 100 }, line: { color: 'D9822B', width: 2.25 } });
  sl.addText('„Nicht Bestandteil dieser Submission. Separate Ausschreibung.“', { x: 5.2, y: 1.85, w: 7.4, h: 1.2, fontFace: FONT_B, fontSize: 26, color: NAVY, italic: true, margin: 0, valign: 'top' });
  sl.addText('“Not part of this tender — tendered separately.”  Tender p. 110, repeated in every ventilation system.', { x: 5.2, y: 3.05, w: 7.4, h: 0.6, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0, valign: 'top' });
  sl.addText([
    { text: 'A product matcher would price it anyway. ', options: { color: NAVY, bold: true } },
    { text: `BidGenius holds ${D.ambiguity} positions for the estimator’s decision:`, options: { color: NAVY } },
  ], { x: 5.2, y: 3.85, w: 7.4, h: 0.8, fontFace: FONT, fontSize: 17, margin: 0, valign: 'top' });
  ['Include', 'Install only', 'Exclude'].forEach((label, i) => {
    const x = 5.2 + i * 2.15;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 4.75, w: 1.95, h: 0.55, rectRadius: 0.08, fill: { color: i === 1 ? NAVY : WHITE }, line: { color: i === 1 ? NAVY : BORDER } });
    sl.addText(label, { x, y: 4.75, w: 1.95, h: 0.55, fontFace: FONT_B, fontSize: 14, color: i === 1 ? WHITE : NAVY, align: 'center', valign: 'middle', margin: 0 });
  });
  sl.addText('— each with a reason, a new revision and a visible CHF effect.', { x: 5.2, y: 5.4, w: 7.4, h: 0.4, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0 });
  band(sl, 'That decision is what protects the margin.');
  sl.addNotes(`THE KEY DEMO MOMENT — slow down, pause after the quote.
"Page 110 says: Nicht Bestandteil dieser Submission — not part of this tender. A product matcher would price it anyway. BidGenius stops and asks: include, install only, or exclude? That's the decision that protects your margin."`);
}

// ============ 8. Measured, not claimed ============
if (want(8)) {
  const sl = contentSlide('IMPACT  ·  FEASIBILITY', 'Measured, not claimed');
  const tiles = [
    [`${D.verified.correct}/${D.verified.total}`, 'verified example positions', 'quantity, unit, catalogue item and system all correct'],
    [`${D.holdout.quantity_and_unit.correct}/${D.holdout.expected_rows}`, 'hand-checked hold-out rows', `${Math.round(D.holdout.quantity_and_unit.among_detected_rate * 100)}% of detected quantities correct`],
    [`${D.pagesDone}/${D.pages}`, 'tender pages processed', 'one partial page flagged for visual review'],
    [`${D.draftSec} s`, 'to a priced, reviewable draft', `local parser, no AI calls, single laptop`],
  ];
  tiles.forEach(([big, label, sub], i) => {
    const x = 0.7 + i * 3.05;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 1.95, w: 2.85, h: 3.4, rectRadius: 0.1, fill: { color: BG }, line: { color: BORDER } });
    sl.addText(big, { x: x + 0.3, y: 2.25, w: 2.5, h: 1.1, fontFace: FONT_B, fontSize: 40, color: i < 2 ? INK : NAVY, margin: 0 });
    sl.addText(label, { x: x + 0.3, y: 3.45, w: 2.4, h: 0.75, fontFace: FONT_B, fontSize: 16, color: NAVY, margin: 0, valign: 'top' });
    sl.addText(sub, { x: x + 0.3, y: 4.25, w: 2.4, h: 0.9, fontFace: FONT, fontSize: 12.5, color: MUTED, margin: 0, valign: 'top' });
  });
  sl.addText('Sources: artifacts/evaluation.json · artifacts/live-holdout-evaluation.json · docs/VALIDATION.md. Sampled evidence — not a claim of whole-tender completeness.', { x: 0.7, y: 5.6, w: 11.9, h: 0.4, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0 });
  band(sl, 'Every claim on this slide can be re-run from the repository.', 6.15);
  sl.addNotes(`Q&A anchor: "How accurate is it?" → "On your 22 verified examples, 22 of 22. On 83 rows we transcribed by hand, it found 80 — and every quantity it found was right. Measured, and in the repo."`);
}

// ============ 9. Design & usability ============
if (want(9)) {
  const sl = contentSlide('DESIGN & USABILITY  ·  15%', 'Usable without training');
  shot(sl, 'workspace', { x: 0.8, y: 1.85, w: 3.75 });
  shot(sl, 'overview_top', { x: 4.8, y: 1.85, w: 3.75 });
  shot(sl, 'assistant', { x: 9.0, y: 1.85, h: 3.95 });
  sl.addText('My workspace: every bid and its state', { x: 0.8, y: 3.55, w: 3.75, h: 0.35, fontFace: FONT_B, fontSize: 13, color: NAVY, margin: 0 });
  sl.addText('Overview: price, gaps, next decision', { x: 4.8, y: 3.55, w: 3.75, h: 0.35, fontFace: FONT_B, fontSize: 13, color: NAVY, margin: 0 });
  const points = [
    ['One question per page', 'Overview · Estimate · Scenarios · Export'],
    ['Review queues by cause', 'missing quantity, quote needed, scope ambiguity…'],
    ['Keyboard-first table', 'j/k to move · Enter to inspect · a to accept'],
    ['Built-in copilot + 5-step tour', 'answers cite positions and pages'],
  ];
  points.forEach(([h, sub], i) => {
    const y = 4.15 + i * 0.5;
    sl.addShape(pptx.ShapeType.ellipse, { x: 0.85, y: y + 0.1, w: 0.14, h: 0.14, fill: { color: INK }, line: { color: INK } });
    sl.addText([{ text: h + '  ', options: { bold: true, color: NAVY } }, { text: sub, options: { color: MUTED } }], { x: 1.1, y, w: 7.5, h: 0.36, fontFace: FONT, fontSize: 14, margin: 0 });
  });
  band(sl, 'Equans look and feel. German source text where estimators expect it. No manual needed.');
  sl.addNotes(`"An estimator opens BidGenius and sees their bids, the price, the gaps and the next decision — no training. If they're unsure, the copilot explains any number and links to the page it came from."`);
}

// ============ 10. Creativity ============
if (want(10)) {
  const sl = contentSlide('CREATIVITY & INNOVATION  ·  10%', 'Three ideas we haven’t seen in estimating tools');
  shot(sl, 'scenarios', { x: 6.25, y: 1.85, w: 6.4 });
  const ideas = [
    ['An honest range, not a hidden gap', `Unpriced scope becomes a benchmark band of ${chfK(D.allowLow)}–${Math.round(D.allowHigh / 1000)}k next to the bid — never inside it.`],
    ['“Which assumption moves the price?”', 'Sensitivity across site efficiency, overhead, margin and rates — check the right thing before signing.'],
    ['Every change is a revision', 'Preview live, apply with a reason, reverse anytime. The bid file explains itself.'],
  ];
  ideas.forEach(([h, body], i) => {
    const y = 1.9 + i * 1.35;
    badge(sl, i + 1, 0.98, y + 0.2, 0.46);
    sl.addText(h, { x: 1.45, y, w: 4.6, h: 0.42, fontFace: FONT_B, fontSize: 18, color: NAVY, margin: 0 });
    sl.addText(body, { x: 1.45, y: y + 0.45, w: 4.6, h: 0.85, fontFace: FONT, fontSize: 13.5, color: MUTED, margin: 0, valign: 'top' });
  });
  band(sl, `Scenarios from your parameters: ${chf(D.aggressive)} · ${grp(D.target)} · ${grp(D.conservative)} — odds labelled illustrative.`);
  sl.addNotes(`Backup / handout for the Scenarios demo beat.
"Before you sign, BidGenius tells you which assumption moves the price most. Change it, see all three bids move, give a reason — new revision."`);
}

// ============ 11. Feasibility ============
if (want(11)) {
  const sl = contentSlide('FEASIBILITY  ·  25%', 'Runs on Azure. Fits your bid process.');
  const lane = (y, label, steps, fill, text) => {
    sl.addText(label, { x: 0.7, y: y - 0.42, w: 6, h: 0.32, fontFace: FONT_B, fontSize: 12, color: INK, charSpacing: 2, margin: 0 });
    const bw = 2.75, gap = 0.3;
    steps.forEach(([h, sub], i) => {
      const x = 0.7 + i * (bw + gap);
      sl.addShape(pptx.ShapeType.roundRect, { x, y, w: bw, h: 1.25, rectRadius: 0.08, fill: { color: fill }, line: { color: fill === WHITE ? BORDER : fill } });
      sl.addText(h, { x: x + 0.2, y: y + 0.14, w: bw - 0.4, h: 0.45, fontFace: FONT_B, fontSize: 15, color: text, margin: 0 });
      sl.addText(sub, { x: x + 0.2, y: y + 0.6, w: bw - 0.4, h: 0.58, fontFace: FONT, fontSize: 11.5, color: text === WHITE ? SOFT : MUTED, margin: 0, valign: 'top' });
      if (i < steps.length - 1) sl.addShape(pptx.ShapeType.line, { x: x + bw + 0.03, y: y + 0.62, w: gap - 0.06, h: 0, line: { color: GREEN, width: 2, endArrowType: 'triangle' } });
    });
  };
  lane(2.15, 'YOUR BID PROCESS', [
    ['Tender in', 'PDF from the tender platform, original kept unchanged'],
    ['Estimator review', 'queues, evidence, reasons, revisions'],
    ['Bid manager sign-off', 'Management view: every bid, status, margin'],
    ['Offer + RFQs out', 'German draft offer, CSV/JSON, supplier requests'],
  ], NAVY, WHITE);
  lane(4.15, 'ON AZURE — SAME CONTAINER AS TODAY', [
    ['Azure Container Apps', 'the existing Docker image, single replica'],
    ['Azure Files at /data', 'SQLite, originals, revisions, exports'],
    ['Azure OpenAI', 'optional · store=false · bounded excerpts'],
    ['Entra ID + PostgreSQL', 'estimator & management roles, multi-user'],
  ], WHITE, NAVY);
  band(sl, 'Runs offline on a laptop today. No integration needed — CSV/JSON into your calculation tool.', 5.95);
  sl.addNotes(`[4:15–4:35] "It runs on a laptop today — and the same container runs on Azure Container Apps. The AI is optional and maps directly to Azure OpenAI in your own tenant. It fits the process you already have: estimator prepares, bid manager signs off, the offer and supplier requests go out."`);
}

// ============ 12. Path to production ============
if (want(12)) {
  const sl = contentSlide('PATH TO PRODUCTION', 'From prototype to pilot in 90 days');
  const phases = [
    ['30 days', 'Prove the value', ['Pilot on 5–10 past Equans tenders', 'Measure time-to-draft vs. today', 'Estimators score trust per position']],
    ['60 days', 'Connect your data', ['Live catalogue and net prices', 'Supplier quotes back into the bid', 'Historical bids to calibrate win odds']],
    ['90 days', 'Run it as a team', ['Entra ID roles and four-eyes sign-off', 'Azure deployment with backups', 'Hand-over into the calculation system']],
  ];
  phases.forEach(([when, head, items], i) => {
    const x = 0.7 + i * 4.05;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 1.95, w: 3.8, h: 3.75, rectRadius: 0.1, fill: { color: i === 0 ? NAVY : WHITE }, line: { color: i === 0 ? NAVY : BORDER }, shadow: i === 0 ? shadow : undefined });
    const dark = i === 0;
    sl.addText(when.toUpperCase(), { x: x + 0.35, y: 2.2, w: 3.1, h: 0.35, fontFace: FONT_B, fontSize: 12, color: dark ? GREEN : INK, charSpacing: 3, margin: 0 });
    sl.addText(head, { x: x + 0.35, y: 2.6, w: 3.1, h: 0.6, fontFace: FONT_B, fontSize: 22, color: dark ? WHITE : NAVY, margin: 0 });
    items.forEach((it, k) => {
      sl.addText([{ text: '›  ', options: { color: dark ? GREEN : INK, bold: true } }, { text: it, options: { color: dark ? SOFT : MUTED } }], { x: x + 0.35, y: 3.45 + k * 0.62, w: 3.2, h: 0.55, fontFace: FONT, fontSize: 14, margin: 0, valign: 'top' });
    });
  });
  band(sl, 'Same pipeline — coverage grows with your catalogue (prototype: 56 products, 22 labour rules).');
  sl.addNotes(`[4:35–4:45] "Next: prove it on your past tenders and measure the time saved, connect your live catalogue and supplier quotes, then roll it out with Entra ID and a four-eyes sign-off."`);
}

// ============ 13. Close ============
if (want(13)) {
  const sl = navySlide();
  waves(sl, 12.3, 1.7);
  sl.addText('BidGenius turns a 202-page tender into a price you can defend — line by line — and tells you exactly what it doesn’t know yet.', { x: 0.8, y: 1.0, w: 9.2, h: 2.4, fontFace: FONT_B, fontSize: 32, color: WHITE, margin: 0, valign: 'top' });
  const score = [
    ['IMPACT 30%', 'A price with an honest range'],
    ['FEASIBILITY 25%', 'Same container → Azure'],
    ['TRACEABILITY 20%', 'Every CHF → its PDF page'],
    ['DESIGN 15%', 'Four pages, no training'],
    ['CREATIVITY 10%', 'Knows when to stop'],
  ];
  score.forEach(([k, v], i) => {
    const x = 0.8 + i * 2.4;
    sl.addShape(pptx.ShapeType.roundRect, { x, y: 4.6, w: 2.25, h: 1.35, rectRadius: 0.08, fill: { color: NAVY2 }, line: { color: GREEN, transparency: 50 } });
    sl.addText(k, { x: x + 0.18, y: 4.75, w: 1.95, h: 0.3, fontFace: FONT_B, fontSize: 11, color: GREEN, charSpacing: 1.5, margin: 0 });
    sl.addText(v, { x: x + 0.18, y: 5.1, w: 1.95, h: 0.75, fontFace: FONT_B, fontSize: 15, color: WHITE, margin: 0, valign: 'top' });
  });
  sl.addText('Thank you.', { x: 0.8, y: 6.5, w: 4, h: 0.4, fontFace: FONT_B, fontSize: 16, color: SOFT, margin: 0 });
  sl.addNotes(`[4:45–5:00] Say the line slowly, then stop talking.
"Equans doesn't need a faster way to produce a wrong number. It needs a price every estimator can defend. BidGenius turns a 202-page tender into a price you can defend, line by line — and tells you exactly what it doesn't know yet. Thank you."`);
}

// ============ 14. Backup: honest limits ============
if (want(14)) {
  const sl = contentSlide('BACKUP  ·  FOR Q&A', 'What we deliberately did not build — yet');
  const items = [
    ['No OCR or drawing take-off', 'Drawings and the Excel take-off are not in the package; missing quantities go to a queue instead of being guessed.'],
    ['No automatic technical approval', '“Fabrikat z.B. … oder gleichwertig” stays an explicit estimator decision, separate from the pricing match.'],
    ['Nothing is sent', 'Supplier RFQs and the German offer are drafts; formal submission stays with the bid team.'],
    ['Illustrative win odds', 'Heuristic from your project parameters until historical bids are imported and explicitly adopted.'],
    ['Demo login', 'Role switch for the demo; production uses Entra ID.'],
  ];
  items.forEach(([h, body], i) => {
    const y = 1.85 + i * 0.86;
    sl.addShape(pptx.ShapeType.rect, { x: 0.7, y, w: 0.07, h: 0.68, fill: { color: GREEN }, line: { color: GREEN } });
    sl.addText(h, { x: 0.95, y: y - 0.02, w: 11.6, h: 0.36, fontFace: FONT_B, fontSize: 17, color: NAVY, margin: 0 });
    sl.addText(body, { x: 0.95, y: y + 0.34, w: 11.6, h: 0.36, fontFace: FONT, fontSize: 13.5, color: MUTED, margin: 0 });
  });
  sl.addNotes('Use only if asked "What did you not build?" — each item is a deliberate safety boundary.');
}

// ============ 15. Backup: numbers & sources ============
if (want(15)) {
  const sl = contentSlide('BACKUP  ·  FOR Q&A', 'Every number in this deck — and where it comes from');
  const rows = [
    ['Included-scope offer', chf(D.offer), `summary.totals.selling_price_chf (revision ${D.revision})`],
    ['Cost baseline · margin', `${chf(D.baseline)} · ${D.margin}%`, 'summary.totals · project_parameters.json'],
    ['Value priced', `${D.pctValue.toFixed(1)}%`, 'summary.completeness.pct_value_priced'],
    ['Positions · priced · unpriced', `${D.positions} · ${D.priced} · ${D.unpriced}`, 'summary.coverage'],
    ['Unpriced benchmark range', `${chf(D.allowLow)} – ${chf(D.allowHigh)}`, 'summary.completeness.allowance_*'],
    ['Full-scope range', `${chf(D.fullLow)} – ${chf(D.fullHigh)}`, 'summary.likely_total_low/high'],
    ['Scope-ambiguity positions', String(D.ambiguity), 'summary.coverage.unresolved_by_cause'],
    ['Scenarios A / T / C', `${chf(D.aggressive)} / ${chf(D.target)} / ${chf(D.conservative)}`, 'summary.scenarios (2.5 / 4.0 / 6.5% margins)'],
    ['Verified examples · hold-out', `${D.verified.correct}/${D.verified.total} · ${D.holdout.quantity_and_unit.correct}/${D.holdout.expected_rows}`, 'artifacts/evaluation.json · live-holdout-evaluation.json'],
    ['Time to priced draft', `${D.draftSec} s (parse ${D.parseSec} s)`, 'docs/VALIDATION.md · evaluation.json'],
  ];
  const hdr = { bold: true, color: WHITE, fill: { color: NAVY }, fontFace: FONT_B };
  const body = (v, i) => ({ text: v, options: { color: NAVY, fill: { color: i % 2 ? WHITE : BG }, fontFace: FONT } });
  sl.addTable([
    [{ text: 'Number', options: hdr }, { text: 'Value', options: hdr }, { text: 'Source', options: hdr }],
    ...rows.map((r, i) => r.map((v) => body(v, i))),
  ], { x: 0.7, y: 1.8, w: 11.9, colW: [3.4, 3.9, 4.6], fontSize: 12.5, rowH: 0.4, border: { type: 'solid', color: BORDER, pt: 0.75 }, valign: 'middle' });
  sl.addNotes(`Generated from project ${projectId} at ${new Date().toISOString()}. Re-run node pitch/build_deck.mjs after resetting the demo so these match the live app.`);
}

await pptx.writeFile({ fileName: OUT });
console.log('Wrote', OUT);
console.log(JSON.stringify({ projectId, ...D, verified: `${D.verified.correct}/${D.verified.total}`, holdout: `${D.holdout.quantity_and_unit.correct}/${D.holdout.expected_rows}` }, null, 1));
