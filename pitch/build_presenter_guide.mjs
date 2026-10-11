import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require('../frontend/node_modules/playwright');
const draft = JSON.parse(fs.readFileSync(path.join(here, 'speaker_draft.json'), 'utf8'));
const out = path.join(here, 'deliverables');
fs.mkdirSync(out, { recursive: true });
const stem = path.join(out, 'BidGenius_AI_Presenter_Guide');
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = seconds => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
const pad = n => String(n).padStart(2, '0');
const sourceFixes = [
  'artifacts/prepared-demo.json; artifacts/live-ai-verification.json',
  'artifacts/prepared-demo.json; README.md',
  'artifacts/live-holdout-evaluation.json; artifacts/live-ai-verification.json',
  'README.md',
  'README.md; docs/ARCHITECTURE.md',
  'Proposed pilot; no measured ROI claim'
];
const qa = draft.qa.map((q, i) => ({ ...q, evidence: sourceFixes[i] }));
qa.splice(2, 0, {
  question: 'Why are so many positions unpriced?',
  answer: 'The supplied starter data contains 56 catalogue references and 22 labour rules. That does not cover every tender item. Unsupported fittings, missing quantities, and unresolved scope need estimator review or supplier quotes. The prototype keeps those gaps visible so they can be resolved before a complete bid is prepared.',
  evidence: 'README.md; supplied catalog.csv and productivity.csv; artifacts/prepared-demo.json'
});
let elapsed = 0;
const short = draft.three_minute_shortcut.slides.map(s => {
  const row = { ...s, title: draft.main[s.slide - 1].title, time_range: `${fmt(elapsed)}–${fmt(elapsed + s.seconds)}` };
  elapsed += s.seconds;
  return row;
});

function thumb(n) {
  const file = path.join(out, 'slide_previews', `slide_${pad(n)}.png`);
  if (!fs.existsSync(file) || fs.statSync(file).size === 0) return '';
  return `<img class="slide-thumb" alt="Preview of slide ${n}" src="data:image/png;base64,${fs.readFileSync(file).toString('base64')}">`;
}
function heading(kicker, title, intro = '') {
  return `<div class="section-heading"><div class="eyebrow">${esc(kicker)}</div><h1>${esc(title)}</h1>${intro ? `<p class="intro">${esc(intro)}</p>` : ''}</div>`;
}
function scriptCard(s) {
  return `<article class="script-card" data-slide="${s.slide}"><div class="card-top"><div class="card-heading"><div class="slide-tag">SLIDE ${pad(s.slide)} <span>${esc(s.time_range)} · ${s.seconds} sec</span></div><h2>${esc(s.title)}</h2><div class="cue"><span>REMEMBER</span> ${esc(s.cue)}</div></div>${thumb(s.slide)}</div><div class="say-label">SAY THIS</div><p class="spoken">${esc(s.script)}</p><div class="direction"><strong>Delivery</strong> ${esc(s.delivery)}</div></article>`;
}

const pages = [];
pages.push({ label: 'Your five-minute cue sheet', kind: 'cheat', html: `${heading('Presenter guide · Hackathon pitch', 'Speak clearly. Let the evidence work.', 'A simple script and calm delivery plan for BidGenius AI. Read the spoken paragraphs; use the cues when you need a reminder.')}
  <div class="stats"><div><strong>5:00</strong><span>total time</span></div><div><strong>10</strong><span>main slides</span></div><div><strong>${draft.spoken_word_count}</strong><span>spoken words</span></div></div>
  <table class="timing"><thead><tr><th>Slide</th><th>Clock</th><th>Your one cue</th></tr></thead><tbody>${draft.main.map(s => `<tr><td><b>${pad(s.slide)}</b></td><td>${esc(s.time_range)}</td><td>${esc(s.cue)}</td></tr>`).join('')}</tbody></table>
  <div class="mint-box"><strong>Before you start</strong><p>Take one slow breath. Look at the judges. Say the opening question, pause, then continue. You do not need to sound dramatic.</p></div>
  <div class="small-note"><b>Demo context.</b> ${esc(draft.snapshot_note)}</div>
  <div class="guide-index"><span>02–06 &nbsp; Full script</span><span>07–08 &nbsp; Judge Q&amp;A</span><span>09–10 &nbsp; Three-minute version</span><span>11 &nbsp; Rehearsal</span></div><div class="view-help"><b>In PowerPoint:</b> use Presenter View to see the notes. Three hidden backup slides (11–13) are available through slide navigation for Q&amp;A.</div>` });

for (let i = 0; i < draft.main.length; i += 2) {
  const pair = draft.main.slice(i, i + 2);
  pages.push({ label: `Full script · Slides ${pair[0].slide}–${pair[1].slide}`, kind: 'script-page', html: `${heading('Five-minute script', `Slides ${pad(pair[0].slide)} + ${pad(pair[1].slide)}`, 'Read the large text aloud. The mint cue and delivery note are just for you.')}<div class="pair">${pair.map(scriptCard).join('')}</div>` });
}
for (const [i, count] of [[0, 4], [4, 3]]) {
  const chunk = qa.slice(i, i + count);
  pages.push({ label: `Judge Q&A · ${i + 1}–${i + chunk.length}`, kind: `qa-page${count === 4 ? ' qa-dense' : ''}`, html: `${heading('Judge Q&A', i === 0 ? 'Answer the question first.' : 'Be clear about the next step.', 'Pause for a moment. Give the direct answer, then one supporting fact. It is fine to say what has not been measured yet.')}<div class="qa-list">${chunk.map((q, ix) => `<article class="qa-card"><div class="question-number">Q${i + ix + 1}</div><h2>${esc(q.question)}</h2><p>${esc(q.answer)}</p><div class="evidence"><b>Evidence to open if asked</b><br>${esc(q.evidence)}</div></article>`).join('')}</div>` });
}
for (let i = 0; i < short.length; i += 5) {
  const chunk = short.slice(i, i + 5);
  pages.push({ label: `Three-minute version · Slides ${chunk[0].slide}–${chunk[4].slide}`, kind: 'short-page', html: `${heading('Three-minute version', `Slides ${pad(chunk[0].slide)}–${pad(chunk[4].slide)}`, i === 0 ? draft.three_minute_shortcut.instruction : 'Keep the sample limitation on slide 7 and the pilot ask on slide 10. Finish calmly; do not speed through the last sentence.')}<div class="short-list">${chunk.map(s => `<article class="short-card"><div class="short-marker">${pad(s.slide)}</div><div><div class="short-clock">${esc(s.time_range)} · ${s.seconds} sec</div><h2>${esc(s.title)}</h2><p>${esc(s.script)}</p></div></article>`).join('')}</div>` });
}
pages.push({ label: 'Rehearsal & pronunciation', kind: 'rehearsal-page', html: `${heading('Rehearsal', 'Make the first minute feel familiar.', 'Practise once for the words, once for the timing, and once standing up with the slides.')}
  <ol class="rehearsal-list">${draft.rehearsal.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
  <h2 class="table-heading">Say the technical words simply</h2><table class="pronunciation"><thead><tr><th>On the slide</th><th>Say it this way</th></tr></thead><tbody>${draft.pronunciation.map(s => `<tr><td>${esc(s.term)}</td><td>${esc(s.say)}</td></tr>`).join('')}</tbody></table>
  <div class="mint-box fallback"><strong>If the live app is unavailable</strong><p>“${esc(draft.demo_fallback.failure_line)}”</p></div>
  <div class="small-note"><b>Default:</b> ${esc(draft.demo_fallback.default)}<br><b>Optional live demo:</b> ${esc(draft.demo_fallback.optional_live)}</div>` });

const css = `
:root{--navy:#10273b;--muted:#516471;--mint:#d9f4e9;--green:#126f60;--line:#dce5e9;--paper:#fff;--light:#f4f8fa}
*{box-sizing:border-box}html,body{margin:0;padding:0}body{font-family:"Segoe UI",Arial,sans-serif;color:var(--navy);background:#e8eef2;-webkit-print-color-adjust:exact;print-color-adjust:exact}
@page{size:A4;margin:0}.sheet{position:relative;width:210mm;height:297mm;padding:15mm 17mm 16mm;background:var(--paper);margin:10mm auto;overflow:hidden;break-after:page;page-break-after:always}.sheet:last-child{break-after:auto;page-break-after:auto}.running-head{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:3mm;margin-bottom:7mm;font-size:8.5pt;font-weight:650;letter-spacing:.08em;text-transform:uppercase}.brand-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#4cbb9b;margin-right:7px}.running-head .label{color:var(--muted);font-size:7.5pt}.footer{position:absolute;bottom:9mm;left:17mm;right:17mm;display:flex;justify-content:space-between;border-top:1px solid var(--line);padding-top:3mm;font-size:8pt;color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:8.5pt;font-weight:750;color:var(--green);margin-bottom:3mm}h1{font-size:27pt;line-height:1.1;letter-spacing:-.035em;margin:0 0 3mm;font-weight:750}h2{font-size:17pt;line-height:1.15;letter-spacing:-.018em;margin:0 0 2mm;font-weight:700}p{margin:0}.intro{font-size:11.5pt;line-height:1.5;color:var(--muted);max-width:164mm}.section-heading{margin-bottom:7mm}.stats{display:grid;grid-template-columns:repeat(3,1fr);background:var(--navy);border-radius:4mm;color:white;padding:6mm 7mm;margin:7mm 0 6mm}.stats div+div{border-left:1px solid #58717f;padding-left:7mm}.stats strong{display:block;font-size:28pt;line-height:1.1;letter-spacing:-.03em}.stats span{display:block;font-size:9pt;line-height:1.8;color:#cee0e9}.timing{border-collapse:collapse;width:100%;font-size:11.5pt;margin-bottom:6mm}.timing th{text-align:left;color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-size:8pt;padding:2mm 3mm;border-bottom:1px solid var(--line)}.timing td{padding:2.35mm 3mm;border-bottom:1px solid var(--line)}.timing td:first-child{width:20mm}.timing td:nth-child(2){width:44mm;color:var(--muted);font-variant-numeric:tabular-nums}.timing tbody tr:nth-child(even){background:var(--light)}.mint-box{background:var(--mint);border-left:3px solid #58aa91;border-radius:0 2.5mm 2.5mm 0;padding:4mm 5mm;font-size:11pt;line-height:1.45;margin-bottom:4mm}.mint-box strong{display:block;font-size:10pt;margin-bottom:1mm}.small-note{font-size:9pt;line-height:1.5;color:var(--muted)}.guide-index{display:grid;grid-template-columns:1fr 1fr;gap:2mm 6mm;margin-top:5mm;font-size:8.5pt;color:var(--muted)}
.cheat .section-heading{margin-bottom:4mm}.cheat .stats{padding:5mm 6mm;margin:5mm 0}.cheat .stats strong{font-size:26pt}.cheat .timing{margin-bottom:4mm}.cheat .timing td{padding:1.85mm 3mm}.cheat .mint-box{font-size:10.5pt}.cheat .small-note{font-size:8.5pt}.view-help{font-size:8.5pt;line-height:1.4;color:var(--muted);margin-top:3mm}
.script-page .section-heading{margin-bottom:6mm}.script-page h1{font-size:25pt}.script-page .intro{font-size:10.5pt}.pair{display:flex;flex-direction:column;gap:7mm}.script-card{border-top:2px solid var(--navy);padding-top:4mm;break-inside:avoid}.card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:5mm;margin-bottom:4mm}.card-heading{flex:1}.slide-tag{font-weight:750;letter-spacing:.1em;font-size:8.5pt;color:var(--green);margin-bottom:2.3mm}.slide-tag span{display:inline-block;letter-spacing:0;color:var(--muted);font-weight:500;margin-left:3mm}.card-top h2{max-width:118mm;font-size:17pt}.cue{font-size:10pt;line-height:1.45;margin-top:2mm;color:var(--green);font-weight:650}.cue span{font-size:7.2pt;letter-spacing:.08em;background:var(--mint);padding:.75mm 1.5mm;margin-right:1mm;border-radius:1mm}.slide-thumb{width:43mm;height:24.19mm;object-fit:contain;border:1px solid var(--line);flex-shrink:0}.say-label{font-size:7.5pt;letter-spacing:.12em;font-weight:750;color:var(--muted);margin-bottom:2mm}.spoken{font-size:15pt;line-height:1.43;letter-spacing:-.007em}.direction{font-size:10pt;line-height:1.45;color:var(--muted);padding:3mm 4mm;background:var(--light);border-radius:2mm;margin-top:4mm}.direction strong{color:var(--navy);margin-right:1mm}
.qa-list{display:flex;flex-direction:column;gap:6mm}.qa-card{position:relative;border-top:1px solid var(--line);padding-top:5mm;padding-left:10mm}.question-number{position:absolute;left:0;top:5mm;font-weight:800;font-size:10pt;color:var(--green)}.qa-card h2{font-size:17pt;max-width:155mm;margin-bottom:3mm}.qa-card p{font-size:13.1pt;line-height:1.5}.evidence{font-size:8.5pt;line-height:1.55;color:var(--muted);margin-top:3mm;overflow-wrap:anywhere}.evidence b{font-weight:600}
.qa-dense .qa-list{gap:4mm}.qa-dense .qa-card{padding-top:3.5mm}.qa-dense .question-number{top:3.5mm}.qa-dense .qa-card h2{font-size:15.5pt;margin-bottom:2mm}.qa-dense .qa-card p{font-size:12pt;line-height:1.43}.qa-dense .evidence{font-size:8pt;margin-top:2mm}.qa-dense .section-heading{margin-bottom:5mm}
.short-list{display:flex;flex-direction:column;gap:5.1mm}.short-card{display:grid;grid-template-columns:10mm 1fr;gap:3mm;border-top:1px solid var(--line);padding-top:4mm}.short-marker{font-size:17pt;font-weight:750;color:var(--green)}.short-clock{color:var(--muted);font-size:8.5pt;margin-bottom:1.5mm}.short-card h2{font-size:13.5pt;margin-bottom:2mm}.short-card p{font-size:13pt;line-height:1.45}
.rehearsal-page .section-heading{margin-bottom:4mm}.rehearsal-page h1{font-size:25pt}.rehearsal-page .intro{font-size:10.5pt}.rehearsal-list{padding-left:6mm;margin:0 0 5mm;font-size:10.8pt;line-height:1.45}.rehearsal-list li{padding-left:1.5mm;margin-bottom:2.1mm}.rehearsal-list li::marker{color:var(--green);font-weight:700}.table-heading{font-size:16pt;margin-bottom:3mm}.pronunciation{border-collapse:collapse;width:100%;font-size:10.5pt;margin-bottom:5mm}.pronunciation th{font-size:8pt;text-align:left;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.pronunciation td,.pronunciation th{padding:2mm 2.5mm;border-bottom:1px solid var(--line)}.pronunciation td:first-child{font-weight:650;width:43mm}.fallback{font-size:10.5pt}.rehearsal-page .small-note{font-size:8.4pt}
@media print{body{background:white}.sheet{margin:0;box-shadow:none}}@media screen{.sheet{box-shadow:0 3mm 12mm #142b3a22}}
`;
const html = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>BidGenius AI — Presenter Guide</title><style>${css}</style></head><body>${pages.map((p, i) => `<section class="sheet ${p.kind}" data-page="${i + 1}"><header class="running-head"><span><i class="brand-dot"></i>BidGenius AI</span><span class="label">Presenter guide</span></header><main>${p.html}</main><footer class="footer"><span>${esc(p.label)}</span><span>${pad(i + 1)} / ${pages.length}</span></footer></section>`).join('')}</body></html>`;
fs.writeFileSync(`${stem}.html`, html, 'utf8');

const md = [
  '# BidGenius AI — Presenter Guide',
  '',
  `**Five-minute pitch · 10 main slides · ${draft.spoken_word_count} spoken words**`,
  '',
  draft.simple_instruction,
  '',
  '**In PowerPoint:** use Presenter View to see the notes. Three hidden backup slides (11–13) are available through slide navigation for Q&A.',
  '',
  '## Timing and cue sheet',
  '',
  '| Slide | Clock | Cue |',
  '| --- | --- | --- |',
  ...draft.main.map(s => `| ${s.slide} | ${s.time_range} | ${s.cue} |`),
  '',
  `**Demo context:** ${draft.snapshot_note}`,
  '',
  '## Five-minute script',
  '',
  ...draft.main.flatMap(s => [`### Slide ${s.slide} — ${s.title}`, '', `**${s.time_range} · ${s.seconds} seconds · Cue: ${s.cue}**`, '', s.script, '', `*Delivery: ${s.delivery}*`, '']),
  '## Judge Q&A',
  '',
  ...qa.flatMap((q, i) => [`### ${i + 1}. ${q.question}`, '', q.answer, '', `Evidence: ${q.evidence}`, '']),
  '## Three-minute version',
  '',
  draft.three_minute_shortcut.instruction,
  '',
  ...short.flatMap(s => [`### Slide ${s.slide} — ${s.title}`, '', `**${s.time_range} · ${s.seconds} seconds**`, '', s.script, '']),
  '## Rehearsal',
  '',
  ...draft.rehearsal.map((s, i) => `${i + 1}. ${s}`),
  '',
  '## Pronunciation',
  '',
  '| On the slide | Say it this way |',
  '| --- | --- |',
  ...draft.pronunciation.map(s => `| ${s.term} | ${s.say} |`),
  '',
  '## Demo fallback',
  '',
  draft.demo_fallback.default,
  '',
  `**If the app is unavailable, say:** “${draft.demo_fallback.failure_line}”`,
  '',
  draft.demo_fallback.optional_live,
  '',
  draft.demo_fallback.honesty,
  ''
].join('\n');
fs.writeFileSync(`${stem}.md`, md, 'utf8');

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1100, height: 1400 }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(`${stem}.html`).href, { waitUntil: 'networkidle' });
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() => document.fonts.ready);
  const checks = await page.evaluate(() => Array.from(document.querySelectorAll('.sheet')).map(sheet => {
    const footer = sheet.querySelector('.footer').getBoundingClientRect();
    const main = sheet.querySelector('main').getBoundingClientRect();
    const children = Array.from(sheet.querySelectorAll('main *'));
    const right = sheet.getBoundingClientRect().right;
    return { page: Number(sheet.dataset.page), contentBottom: Math.round(main.bottom), footerTop: Math.round(footer.top), clearance: Math.round(footer.top - main.bottom), horizontalOverflows: children.filter(el => el.getBoundingClientRect().right > right + 1).length };
  }));
  const bad = checks.filter(s => s.clearance < 7 || s.horizontalOverflows > 0);
  if (bad.length) throw new Error(`Guide layout overflow: ${JSON.stringify(bad)}`);
  await page.pdf({ path: `${stem}.pdf`, format: 'A4', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
  console.log(JSON.stringify({ pdf: `${stem}.pdf`, pages: pages.length, words: draft.spoken_word_count, minFooterClearancePx: Math.min(...checks.map(s => s.clearance)), checks }, null, 2));
} finally {
  await browser.close();
}
