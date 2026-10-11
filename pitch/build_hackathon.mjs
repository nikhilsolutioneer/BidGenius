// Reproducible presentation. Uses saved demo screenshots and measured artifacts.
// Does not read or change the running estimator workspace.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import PptxGenJS from 'pptxgenjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const ASSET = path.join(HERE, 'presentation_assets');
const OUT = path.join(HERE, 'deliverables');
fs.mkdirSync(OUT, {recursive:true});
const dims = JSON.parse(fs.readFileSync(path.join(ASSET,'dimensions.json'),'utf8'));
const read = rel => JSON.parse(fs.readFileSync(path.join(ROOT,rel),'utf8'));
const prepared = read('artifacts/prepared-demo.json');
const evalJ = read('artifacts/evaluation.json');
const holdout = read('artifacts/live-holdout-evaluation.json').holdout;
const notesFile = path.join(HERE,'speaker_draft.json');
const notes = fs.existsSync(notesFile) ? JSON.parse(fs.readFileSync(notesFile,'utf8').replace(/^\uFEFF/,'')) : {};
const scriptSlides = Array.isArray(notes) ? notes : (notes.slides || notes.main || []);
const pptx = new PptxGenJS();
pptx.layout='LAYOUT_WIDE';
pptx.author='BidGenius AI';
pptx.subject='Equans hackathon project pitch and presenter notes';
pptx.title='BidGenius AI | A first price you can explain';
pptx.company='BidGenius AI project';
pptx.lang='en-GB';
pptx.theme={headFontFace:'Segoe UI Semibold',bodyFontFace:'Segoe UI',lang:'en-GB'};
const W=13.333333,H=7.5;
const C={navy:'002B3D',deep:'002131',panel:'0A3C4C',mint:'83D6B2',green:'267654',white:'FFFFFF',paper:'F4F7F5',light:'E6F3EC',muted:'536B76',soft:'B6CCD1',line:'D6E2DE',amber:'F2C780',amberInk:'83500F'};
const F='Segoe UI', B='Segoe UI Semibold';
const shapes=[];
function rect(s,x,y,w,h,fill,opts={}) {s.addShape(pptx.ShapeType.rect,{x,y,w,h,fill:{color:fill},line:{color:fill,transparency:100},...opts});}
function line(s,x,y,w,h,color=C.line,width=1){s.addShape(pptx.ShapeType.line,{x,y,w,h,line:{color,width}});}
function text(s,txt,x,y,w,h,size=20,color=C.navy,opts={}) {
  s.addText(txt,{x,y,w,h,fontFace:F,fontSize:size,color,margin:0,breakLine:false,valign:'mid',paraSpaceAfterPt:0,...opts});
  shapes.push({slide:pptx._slides.length,text:typeof txt==='string'?txt:JSON.stringify(txt),x,y,w,h,size});
}
function label(s,txt,x,y,w=10,dark=false){text(s,txt,x,y,w,.26,11,dark?C.mint:C.green,{fontFace:B,charSpacing:2.1});}
function dot(s,x,y,d=.08,fill=C.mint){s.addShape(pptx.ShapeType.ellipse,{x,y,w:d,h:d,fill:{color:fill},line:{color:fill,transparency:100}});}
function pill(s,txt,x,y,w,fill=C.light,color=C.green){rect(s,x,y,w,.34,fill);text(s,txt,x+.1,y,w-.2,.34,10.5,color,{fontFace:B,align:'center'});}
function image(s,name,x,y,w,h){
 const [iw,ih]=dims[name];if(!h)h=w*ih/iw;
 s.addImage({path:path.join(ASSET,name+'.png'),x,y,w,h,altText:`Actual BidGenius AI ${name} interface, prepared demo snapshot`});
 return {w,h};
}
function footer(s,n,dark=false,backup=false){
 line(s,.6,7.06,12.13,0,dark?C.panel:C.line,.65);
 text(s,'BidGenius AI  /  Equans challenge',.6,7.16,6,.18,9,dark?C.soft:C.muted);
 text(s,backup?'Q&A  /  '+String(n-10).padStart(2,'0'):String(n).padStart(2,'0')+'  /  10',11.2,7.14,1.52,.2,9,dark?C.soft:C.muted,{align:'right'});
}
function base(n,tag,title,{dark=false,backup=false}={}){
 const s=pptx.addSlide();s.background={color:dark?C.navy:C.paper};
 if(backup)s.hidden=true;
 label(s,tag,.65,.43,11,dark);
 text(s,title,.65,.95,12.05,.78,35,dark?C.white:C.navy,{fontFace:B});
 footer(s,n,dark,backup);return s;
}
function addNote(s,n,extra=''){
 const d=scriptSlides.find(x=>Number(x.slide??x.number??x.slide_number)===n)||scriptSlides[n-1];
 let note=d ? [d.title,d.time||d.timing||d.time_range,d.cue?'CUE: '+d.cue:'',d.script||d.spoken||d.transcript||'',d.delivery||d.direction||''].filter(Boolean).join('\n\n') : '';
 if(!note)note='Use the matching slide in BidGenius_AI_Presenter_Guide. Main slides 1–10 total approximately five minutes.';
 s.addNotes(note+'\n\nEVIDENCE / PRESENTER REFERENCE\n'+extra);
}

// 01 — The opening has a deliberately quiet, single visual idea.
{
const s=pptx.addSlide();s.background={color:C.navy};
label(s,'EQUANS CHALLENGE  /  WORKING PROTOTYPE',.72,.55,10,true);
text(s,'BidGenius',.72,1.42,6.6,.7,32,C.white,{fontFace:B});pill(s,'AI',3.22,1.63,.55,C.mint,C.navy);
text(s,'A first price.\nYou can explain.',.68,2.26,8.35,2.05,53,C.white,{fontFace:B,breakLine:false});
text(s,'From a 202-page tender to a reviewable estimate.',.76,4.67,6.5,.77,21,C.soft);
// Editable document → evidence motif.
rect(s,9.1,1.67,3.13,3.94,C.panel);rect(s,8.84,1.95,3.13,3.94,'145063');rect(s,8.57,2.22,3.13,3.94,C.white);
label(s,'TENDER',8.87,2.58,2.2);
text(s,'202',8.82,2.94,2.54,1.2,70,C.navy,{fontFace:B});
text(s,'pages of source evidence',8.91,4.22,2.24,.54,14,C.muted);
for(let i=0;i<4;i++)line(s,8.91,4.98+i*.2,i===2?1.55:2.35,0,C.line,2);
rect(s,7.93,5.77,4.22,.62,C.mint);text(s,'REVIEW  →  EXPLAIN  →  DECIDE',8.15,5.77,3.8,.62,12,C.navy,{fontFace:B,charSpacing:.8});
footer(s,1,true);addNote(s,1,'Challenge: Schulhaus_Oberglatt_Hackathon_Starter_Package_v2/README.md. This is a prototype and first estimate, not a complete procurement submission.');
}

// 02 — Establish the actual tender and the estimator's job.
{
const s=base(2,'THE PROBLEM','202 pages. One pricing decision.');
text(s,'202',.62,1.95,5.15,2.15,126,C.navy,{fontFace:B});
text(s,'pages in the Oberglatt\nventilation tender',.77,4.2,4.65,.83,25,C.muted);
line(s,6.0,2.12,0,3.61,C.line,1);
const rows=[['01','Find the scope','What is included, missing or unclear?'],['02','Price the work','Connect quantities, products and labour.'],['03','Explain the gaps','Show which decisions still need a person.']];
rows.forEach((r,i)=>{const y=2.12+i*1.21;label(s,r[0],6.43,y+.05,.6);text(s,r[1],7.16,y,5.2,.42,24,C.navy,{fontFace:B});text(s,r[2],7.16,y+.48,5.1,.55,17,C.muted);});
rect(s,.7,6.12,11.95,.56,C.light);text(s,'This tender excludes price negotiations. The first estimate matters.',.94,6.13,11.5,.52,18,C.navy,{fontFace:B});
addNote(s,2,'Original tender, physical PDF page 9, section 1.17: Preisverhandlungen Ausgeschlossen. Source PDF has 202 pages. No claimed estimate of manual time or financial loss.');
}

// 03 — Actual product, with the division of responsibility in plain language.
{
const s=base(3,'THE WORKSPACE','Read. Match. Calculate. Review.');
image(s,'overview',.7,1.99,11.95);
const roles=[['AI proposes','Interpretation + candidate matches'],['Code calculates','Material + labour + assumptions'],['Estimator decides','Review + reasons + revisions']];
roles.forEach((r,i)=>{const x=.78+i*4.05;label(s,String(i+1).padStart(2,'0'),x,6.07,.42);text(s,r[0],x+.47,6.02,3.42,.35,19,C.navy,{fontFace:B});text(s,r[1],x+.47,6.42,3.42,.28,12,C.muted);});
addNote(s,3,'Screenshot: pitch/shots/overview.png, prepared demo revision 1. Indicative included-scope CHF 1,661,000; 542 unpriced positions remain in this snapshot. Snapshot is not live workspace state. Optional AI may propose; authoritative Decimal arithmetic is in backend/tenderproof/pricing.py. AI does not approve prices.');
text(s,'Prepared demo snapshot · included scope · estimator review required',.78,1.8,11.5,.16,8.5,C.muted);
}

// 04 — An evidence trail, with a legible real inspector panel.
{
const s=base(4,'TRACEABILITY','Open the price. See the proof.');
const rows=[['310 m²','Quantity from PDF page 113','LA02 · thermal insulation'],['P-INS-002','Catalogue pricing reference','60 mm mineral wool insulation'],['Labour rule','Hours, site factors and rate','Calculation inputs stay inspectable']];
rows.forEach((r,i)=>{const y=2.09+i*1.35;dot(s,.83,y+.15,.16,C.green);if(i<2)line(s,.91,y+.39,0,.93,C.line,2);text(s,r[0],1.23,y,6.63,.53,i===0?31:25,C.navy,{fontFace:B});text(s,r[1],1.25,y+.58,6.3,.35,18,C.navy);text(s,r[2],1.25,y+.97,6.3,.28,13,C.muted);});
rect(s,8.53,1.9,4.13,4.97,C.line);image(s,'inspector',8.57,1.94,4.05);
text(s,'A price reference still needs technical review.',.79,6.51,7.1,.35,16,C.green,{fontFace:B});
addNote(s,4,'Source screenshot pitch/shots/inspector-calc.png: LA02 physical p.113 #2, 310 m², P-INS-002. Catalogue confirms 60 mm mineral wool duct insulation. Pricing confidence is not technical equivalence. Project factors and labour rules have their own source data, not necessarily the PDF.');
}

// 05 — A concrete ambiguity is more convincing than generic AI claims.
{
const s=base(5,'THE MOMENT THAT MATTERS','“This needs your decision.”',{dark:true});
rect(s,.73,2.02,5.6,3.65,C.white);image(s,'scope',.87,2.18,5.32);
// Highlight the actual exclusion sentence without obscuring it.
s.addShape(pptx.ShapeType.rect,{x:1.53,y:3.39,w:4.38,h:.25,fill:{color:C.amber,transparency:72},line:{color:C.amber,width:1.2}});
text(s,'Original tender · page 110',.79,5.83,5.4,.27,11,C.soft);
label(s,'SCOPE AMBIGUITY',6.88,2.13,5,true);
text(s,'“Not part of this tender.\nTendered separately.”',6.86,2.62,5.66,1.04,29,C.white,{fontFace:B});
text(s,'The page also lists field devices.\nThe estimator resolves the scope.',6.91,3.93,5.29,.9,19,C.soft);
['Include','Install only','Exclude'].forEach((t,i)=>pill(s,t,6.9+i*1.79,5.11,1.61,i===1?C.mint:C.panel,i===1?C.navy:C.white));
text(s,'Record a reason. Create a revision.',6.91,5.75,5.55,.53,19,C.mint,{fontFace:B});
text(s,'Unknown scope stays visible until it is reviewed.',.81,6.49,11.5,.32,19,C.white);
addNote(s,5,'Original PDF page 110: controls/regulation exclusion followed by field-device installation wording. This is ambiguous scope, not a claim that everything on the page must be excluded. Screenshot is a saved prototype view. Choices require estimator rationale and create a revision.');
}

// 06 — Decision support, explicitly assumption-based.
{
const s=base(6,'BID SCENARIOS','Compare the bid before committing.');
label(s,'THREE STRATEGIES / SAME INCLUDED SCOPE',.84,2.1,11.5);
image(s,'scenario_cards',.72,2.77,11.88);
text(s,'Preview → Compare → Apply with a reason',.84,6.08,11.66,.47,25,C.navy,{fontFace:B});
text(s,'Prepared demo snapshot. Win probabilities are illustrative; included scope only.',.84,6.79,11.7,.21,10,C.muted);
addNote(s,6,'Prepared screenshot: bid scenarios CHF 1,610,000 / CHF 1,635,000 / CHF 1,678,000, requested margins 2.5% / 4.0% / 6.5%. Source project_parameters.json stretch_bid_optimization and pitch/shots/scenarios.png. Scenario margins differ from saved offer target margin of 5.5%. Win probabilities are heuristics, not calibrated predictions or a statistical optimum.');
}

// 07 — Measurements from distinct runs are visibly separate.
{
const s=base(7,'MEASURED EVIDENCE','Fast to a draft. Clear about the limits.');
label(s,'PREPARED LOCAL RUN',.81,2.05,5.1);
text(s,Math.round(prepared.processing_seconds)+' s',.71,2.34,5.4,1.58,92,C.navy,{fontFace:B});
text(s,'to a reviewable first draft',.83,3.98,5.1,.52,25,C.navy,{fontFace:B});
text(s,'202 pages attempted · one partial page\nSingle laptop · no AI call in this run',.84,4.69,5.28,.93,18,C.muted);
line(s,6.36,2.03,0,3.58,C.line,1);
label(s,'SEPARATE AI + LOCAL RUN',6.83,2.05,5.66);
text(s,`${holdout.quantity_and_unit.correct}/${holdout.expected_rows}`,6.75,2.43,5.5,1.3,73,C.navy,{fontFace:B});
text(s,'sample rows detected with\ncorrect quantity and unit',6.86,3.98,5.46,.91,23,C.navy,{fontFace:B});
text(s,'Purposive sample; does not establish\ncomplete extraction or pricing accuracy.',6.87,5.04,5.48,.66,16,C.muted);
rect(s,.76,6.05,11.89,.67,C.light);
text(s,`${evalJ.verified_examples.complete_row.correct}/22 supplied examples reproduced`,.98,6.08,6.6,.57,21,C.green,{fontFace:B});
text(s,'Quantity · unit · reference · system',7.55,6.16,4.8,.35,14,C.muted,{align:'right'});
text(s,'Sources: prepared-demo.json · evaluation.json · live-holdout-evaluation.json (10 Oct 2026)',.84,6.82,11.7,.16,8.5,C.muted);
addNote(s,7,'55.035 s = artifacts/prepared-demo.json, local end-to-end import/draft. 22/22 = artifacts/evaluation.json supplied examples. 80/83 = artifacts/live-holdout-evaluation.json; frozen purposive sample from separate live mixed AI/local run. Latest live artifact records 38 successful AI batches and 15 fallbacks. Do not describe 55 seconds as live AI latency or 80/83 as price accuracy. No manual-review time saving was measured.');
}

// 08 — The output carries the reasoning into a real estimator workflow.
{
const s=base(8,'HANDOVER','The estimate travels with its evidence.');
rect(s,.75,2.12,5.07,4.53,C.navy);label(s,'ONE REVISION',1.08,2.51,4.1,true);
text(s,'Estimate\n+ evidence\n+ open questions',1.07,3.07,4.18,1.76,31,C.white,{fontFace:B});
text(s,'A draft package the next\nreviewer can inspect.',1.09,5.25,4.07,.82,20,C.soft);
const items=[['Draft offer','German printable estimate'],['Structured data','CSV, JSON and calculation inputs'],['Review package','Source PDF, assumptions and issues']];
items.forEach((r,i)=>{const y=2.26+i*1.27;label(s,String(i+1).padStart(2,'0'),6.3,y+.04,.56);text(s,r[0],7.09,y,5.4,.4,23,C.navy,{fontFace:B});text(s,r[1],7.09,y+.52,5.4,.47,18,C.muted);if(i<2)line(s,6.33,y+1.08,6.26,0,C.line,.8);});
text(s,'Exports stay tied to the saved revision.',6.37,6.26,6.06,.45,18,C.green,{fontFace:B});
addNote(s,8,'README and backend/tenderproof/exports.py: pinned-revision CSV, JSON, German printable HTML and offline ZIP containing source PDF and review data. Supplier RFQs are unsent drafts. No automatic procurement submission. The review package is not a completed approved tender.');
}

// 09 — A proposal to test value, not fabricated ROI.
{
const s=base(9,'PROPOSED NEXT STEP','Prove the value with estimators.');
text(s,'5–10',.72,1.98,5.23,1.56,90,C.navy,{fontFace:B});
text(s,'historical tenders\nfor a proposed pilot',.87,3.69,5.16,.91,25,C.muted);
const rows=[['Test','Compare against reviewed estimates.'],['Measure','Review time, corrections and coverage.'],['Connect','Current supplier data and team controls.']];
rows.forEach((r,i)=>{const y=2.08+i*1.22;dot(s,6.3,y+.13,.16,C.green);text(s,r[0],6.69,y,5.8,.4,24,C.navy,{fontFace:B});text(s,r[1],6.7,y+.48,5.85,.57,17,C.muted);});
rect(s,.77,5.87,11.83,.77,C.light);text(s,'Pilot success = less review effort, with errors and gaps still visible.',1.01,5.94,11.35,.58,21,C.navy,{fontFace:B});
text(s,'Pilot proposal; time savings and commercial impact have not yet been measured.',.89,6.8,11.8,.19,9,C.muted);
addNote(s,9,'Proposed pilot, not an agreed deployment or evidence of customer adoption. Current prototype is local/single estimator; organizational login, multiuser workflow and supplier integrations require further engineering and validation. 5–10 is an illustrative pilot scope chosen for the pitch.');
}

// 10 — End with a sentence the presenter can remember.
{
const s=pptx.addSlide();s.background={color:C.navy};label(s,'BIDGENIUS AI',.78,.67,10,true);
text(s,'Read the tender.\nSee the gaps.\nDefend the price.',.73,1.85,11.85,3.1,55,C.white,{fontFace:B});
rect(s,.76,4.93,7.37,.1,C.mint);
text(s,'Next: a measured pilot with Equans estimators.',.82,5.55,11.6,.59,24,C.mint,{fontFace:B});
text(s,'Thank you.',.83,6.41,8,.32,18,C.soft);
footer(s,10,true);addNote(s,10,'Stop here for the main presentation. Backup slides 11–13 are hidden and can be opened by slide number during Q&A. No guarantee of winning the hackathon or measured ROI is claimed.');
}

// 11 — Technical appendix, hidden during the main pitch.
{
const s=base(11,'BACKUP / HOW IT WORKS','AI interprets. Code prices. People approve.',{backup:true});
const boxes=[['Source inputs','PDF + catalogue\n+ productivity rules'],['Interpretation','Local parsing\n+ optional AI proposals'],['Calculation','Validated inputs\n+ Decimal arithmetic'],['Review + export','Reasons + revisions\n+ pinned snapshots']];
boxes.forEach((b,i)=>{const x=.76+i*3.05;rect(s,x,2.34,2.82,2.05,i===2?C.navy:C.white);label(s,'0'+(i+1),x+.22,2.57,2,i===2);text(s,b[0],x+.22,3.03,2.42,.45,19,i===2?C.white:C.navy,{fontFace:B});text(s,b[1],x+.22,3.55,2.39,.61,14,i===2?C.soft:C.muted);if(i<3)text(s,'→',x+2.82,3.05,.24,.3,17,C.green,{align:'center'});});
text(s,'React + TypeScript  →  FastAPI  →  SQLite + local files',.89,4.93,11.8,.49,22,C.navy,{fontFace:B});
text(s,'LangGraph checkpoints preserve completed processing batches.',.9,5.66,11.5,.43,18,C.muted);
text(s,'Local review works offline. Optional AI sends selected excerpts to an external API.',.9,6.3,11.6,.47,17,C.green);
addNote(s,11,'docs/ARCHITECTURE.md; backend modules. Current single-estimator local prototype. Optional OpenAI interpretation does not approve prices or technical equivalence. store=False is not a guarantee of zero retention. Azure deployment is not asserted.');
}

// 12 — Honest answers are concise and prepared.
{
const s=base(12,'BACKUP / SCOPE','What still needs validation?',{backup:true});
const rows=[['Coverage','Page attempts do not prove complete extraction.\nPage 201, drawings and missing quantities need review.'],['Pricing','Supplier references are provisional.\nCatalogue match does not approve technical equivalence.'],['Bid probabilities','Scenario assumptions are illustrative.\nHistorical data is needed for calibration.'],['Team deployment','Authentication and multiuser collaboration remain future work.\nFormal tender submission stays with the bid team.']];
rows.forEach((r,i)=>{const y=2.06+i*1.13;rect(s,.77,y,.055,.82,C.green);text(s,r[0],1.02,y,3.18,.42,22,C.navy,{fontFace:B});text(s,r[1],4.35,y,8.12,.82,17,C.muted);if(i<3)line(s,1.02,y+.99,11.55,0,C.line,.7);});
addNote(s,12,'README known scope limits and docs/ARCHITECTURE.md. The supplied reference set has 56 catalogue rows and 22 installation rules. No OCR or drawing takeoff. Existing screenshots are a prepared R1 snapshot, not current live state.');
}

// 13 — Provenance for the numerically curious judge.
{
const s=base(13,'BACKUP / EVIDENCE REGISTER','The numbers and their sources.',{backup:true});
const rows=[
 ['Prepared local draft','55.035 s · 202 pages attempted','artifacts/prepared-demo.json'],
 ['Prepared extraction','679 records · 542 unpriced','artifacts/prepared-demo.json'],
 ['Included-scope draft price','CHF 1,661,000 · revision 1','artifacts/prepared-demo.json'],
 ['Supplied examples','22/22 across evaluated fields','artifacts/evaluation.json'],
 ['Live run sample','80/83 detected + quantity/unit correct','artifacts/live-holdout-evaluation.json'],
 ['Golden example LV0001','CHF 806.26 direct position cost','Starter package: expected_output_example.json'],
 ];
rect(s,.78,2.06,11.82,.48,C.navy);['MEASUREMENT','RESULT','LOCAL SOURCE'].forEach((t,i)=>text(s,t,[.98,4.05,8.11][i],2.06,[2.9,3.9,4.3][i],.48,11,C.white,{fontFace:B}));
rows.forEach((r,i)=>{const y=2.57+i*.52;rect(s,.78,y,11.82,.49,i%2?C.paper:C.white);text(s,r[0],.98,y,2.95,.49,12.5,C.navy,{fontFace:B});text(s,r[1],4.05,y,3.93,.49,12.2,C.navy);text(s,r[2],8.11,y,4.27,.49,10.2,C.muted);});
text(s,'Prepared financial snapshot: 10 October 2026. Provisional prices; unresolved scope remains.',.87,5.96,11.68,.44,15,C.muted);
text(s,'The 55-second local draft and the live AI sample are separate runs.',.87,6.53,11.68,.36,17,C.green,{fontFace:B});
addNote(s,13,'Use current JSON artifacts as the source of measurements. docs/VALIDATION.md contains older parser/live batch counts. Prepared-demo.json counted 137 priced before UI separated 112 priced and 25 included elsewhere; both correspond to 542 unpriced of 679 extracted. Deck avoids mixing these categories. Current running workspace has later revisions and can differ from screenshots.');
}

const bad=shapes.filter(q=>q.x<0||q.y<0||q.x+q.w>W+.01||q.y+q.h>H+.01);
if(bad.length)throw new Error('Out of slide bounds: '+JSON.stringify(bad));
await pptx.writeFile({fileName:path.join(OUT,'BidGenius_AI_Hackathon.pptx')});
fs.writeFileSync(path.join(OUT,'layout_manifest.json'),JSON.stringify(shapes,null,2));
console.log(`Created ${pptx._slides.length} slides (10 main + 3 hidden Q&A), ${shapes.length} text objects, with speaker notes.`);
