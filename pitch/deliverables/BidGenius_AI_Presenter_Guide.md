# BidGenius AI — Presenter Guide

**Five-minute pitch · 10 main slides · 521 spoken words**

Read only the script paragraphs aloud. Cue words and delivery instructions are reminders, not spoken text. Use the pauses to point at the evidence.

**In PowerPoint:** use Presenter View to see the notes. Three hidden backup slides (11–13) are available through slide navigation for Q&A.

## Timing and cue sheet

| Slide | Clock | Cue |
| --- | --- | --- |
| 1 | 0:00–0:25 | Explain the price |
| 2 | 0:25–0:50 | Three jobs |
| 3 | 0:50–1:20 | People decide |
| 4 | 1:20–1:55 | Follow one line |
| 5 | 1:55–2:25 | Read the exclusion |
| 6 | 2:25–2:50 | Compare assumptions |
| 7 | 2:50–3:40 | Three separate checks |
| 8 | 3:40–4:05 | Carry the evidence |
| 9 | 4:05–4:35 | Pilot, then measure |
| 10 | 4:35–5:00 | Make the ask |

**Demo context:** Screenshots and prepared-run numbers refer to the documented 10 October 2026 revision 1 snapshot. The current saved workspace contains later user edits. Do not describe a screenshot as a fresh live run or assume current financial values match it.

## Five-minute script

### Slide 1 — A first price you can explain

**0:00–0:25 · 25 seconds · Cue: Explain the price**

Imagine being asked to defend a tender price, line by line. Could you show where every number came from? We built BidGenius AI to help estimators reach a first price they can explain, with the source, the calculation, and the open questions together.

*Delivery: Start looking at the judges. Pause after the question, then say the product name slowly.*

### Slide 2 — 202 pages, one pricing decision

**0:25–0:50 · 25 seconds · Cue: Three jobs**

Our case is a two-hundred-and-two-page ventilation tender for a school in Oberglatt, Switzerland. An estimator must understand the scope, connect it to catalogue references, and calculate installation labour. Those jobs are connected. Miss a quantity or misunderstand an exclusion, and the price can look precise while the underlying decision is wrong.

*Delivery: Point once to each of the three jobs. Do not read every label.*

### Slide 3 — Read, match, calculate, review

**0:50–1:20 · 30 seconds · Cue: People decide**

This is a prepared snapshot of the working application. It reads the documents, proposes matches, calculates costs, and brings unresolved items into review. AI can help interpret the text and suggest references. The maths follows explicit rules. The estimator makes the decision. This overview shows the draft price and what still needs attention.

*Delivery: Point to the overview screenshot, then look back at the judges for the final two sentences.*

### Slide 4 — Open the price, see the proof

**1:20–1:55 · 35 seconds · Cue: Follow one line**

Take this insulation line from system L A zero two. Page one hundred and thirteen specifies three hundred and ten square metres. We can open that evidence, inspect catalogue reference P INS zero zero two, and follow the labour rule. That makes the cost explainable. The reference still needs review; it does not prove technical equivalence.

*Delivery: Move your pointer from source evidence to catalogue reference to labour. Say the quantities slowly.*

### Slide 5 — Needs your decision

**1:55–2:25 · 30 seconds · Cue: Read the exclusion**

Now look at page one hundred and ten. A note flags scope for a separate tender, while nearby items can still carry installation obligations. The estimator must check which instruction applies. They can include a position, keep installation only, or exclude it. A reason and a new revision preserve how that decision changed the estimate.

*Delivery: Point to the German note, then to the three scope choices. Explain the ambiguity without implying everything on page 110 is excluded.*

### Slide 6 — Compare the bid before committing

**2:25–2:50 · 25 seconds · Cue: Compare assumptions**

Next, we compare aggressive, target, and conservative bids. The estimator can preview changes and see the effect on price, margin, and contribution before accepting them. The displayed win probabilities are illustrative assumptions. They help explore a decision, but they are not reliable predictions of winning.

*Delivery: Trace the three scenario cards with one gesture. Emphasize the word 'illustrative'.*

### Slide 7 — What we measured

**2:50–3:40 · 50 seconds · Cue: Three separate checks**

Here is the evidence, with the tests kept separate. One prepared local run produced a draft in about fifty-five seconds. It attempted all two hundred and two pages, with one partial page. A separate live run, combining AI and local fallbacks, found eighty of eighty-three sampled rows and their explicit quantities and units. That measures extraction on a selected sample, not pricing accuracy. The local checks also passed all twenty-two supplied examples. These results support a prototype; they do not prove a complete tender.

*Delivery: Slow down. Pause between the local run, live sample, and supplied examples. Do not read the decimal seconds aloud.*

### Slide 8 — Complete the handover

**3:40–4:05 · 25 seconds · Cue: Carry the evidence**

The output is a reviewable handover. It includes source evidence, the cost build-up, unresolved scope, and draft exports tied to a specific revision. Another estimator can see what was included, what was assumed, and what still needs a decision.

*Delivery: Point to the handover items, then say the last sentence to the judges.*

### Slide 9 — Prove value with estimators

**4:05–4:35 · 30 seconds · Cue: Pilot, then measure**

Our next step is a pilot with estimators using five to ten historical tenders. We would measure review time, corrections, and pricing coverage against their existing process. We also need real supplier quotes, authentication, and team collaboration. We have not measured return on investment yet. The pilot should tell us where the product creates value.

*Delivery: Present the pilot as a proposal. Keep your voice steady when naming the remaining work.*

### Slide 10 — Read the tender. See the gaps. Defend the price.

**4:35–5:00 · 25 seconds · Cue: Make the ask**

BidGenius AI brings the tender, the estimate, and the reasons behind it into one workspace. Read the tender. See the gaps. Defend the price. We are asking for an estimator partner and historical tenders to run that pilot. Thank you.

*Delivery: Look at the judges. Pause between the three short lines, make the ask, and stop after 'Thank you'.*

## Judge Q&A

### 1. Was the fifty-five-second result an AI run?

No. The 55.035-second measurement was one prepared local-parser run on this laptop. It made no model calls. The separate live AI run used AI and local validation fallbacks; we report its extraction sample separately.

Evidence: artifacts/prepared-demo.json; artifacts/live-ai-verification.json

### 2. Is this a complete price ready to submit?

It is a draft for estimator review. The prepared snapshot has 542 unpriced positions, one partially readable page, and unresolved scope. Supplier quotes and referenced drawings are still missing. The product exports the gaps along with the estimate.

Evidence: artifacts/prepared-demo.json; README.md

### 3. Why are so many positions unpriced?

The supplied starter data contains 56 catalogue references and 22 labour rules. That does not cover every tender item. Unsupported fittings, missing quantities, and unresolved scope need estimator review or supplier quotes. The prototype keeps those gaps visible so they can be resolved before a complete bid is prepared.

Evidence: README.md; supplied catalog.csv and productivity.csv; artifacts/prepared-demo.json

### 4. How accurate is the AI?

In a selected 83-row sample, the mixed AI and local-fallback run detected 80 rows and correctly captured explicit quantity and unit for those 80. This does not measure complete-tender recall, precision, technical equivalence, or pricing accuracy. We need broader evaluation with estimators.

Evidence: artifacts/live-holdout-evaluation.json; artifacts/live-ai-verification.json

### 5. Why use this instead of a spreadsheet?

The prototype links an estimate line to its source evidence, catalogue reference, installation rule, and recorded review decision. It also preserves revisions and exports the unresolved items. The pilot should test whether those links make review faster and more reliable.

Evidence: README.md

### 6. Is it ready for production, and where does data go?

The current prototype is a local, single-user workspace. Ordinary review and calculation work locally. Optional AI processing sends selected source excerpts and catalogue data to an external OpenAI service. Authentication, team collaboration, and production deployment controls still need work.

Evidence: README.md; docs/ARCHITECTURE.md

### 7. What savings or return on investment have you proven?

We have measured processing and sample checks, but not customer time savings or return on investment. The proposed historical-tender pilot would compare review time, corrections, and coverage against the existing estimator process.

Evidence: Proposed pilot; no measured ROI claim

## Three-minute version

Use these shorter lines with the same ten slides; do not skip the sample limitation or pilot ask.

### Slide 1 — A first price you can explain

**0:00–0:15 · 15 seconds**

Could you defend a tender price, line by line? BidGenius AI helps estimators reach a first price they can explain.

### Slide 2 — 202 pages, one pricing decision

**0:15–0:30 · 15 seconds**

Our case is a two-hundred-and-two-page ventilation tender. Estimators must understand scope, find catalogue references, and calculate installation labour. Missing one link weakens the price.

### Slide 3 — Read, match, calculate, review

**0:30–0:50 · 20 seconds**

This prepared screenshot shows the working application: read, match, calculate, review. AI proposes interpretations and references. Explicit rules calculate the costs. The estimator makes the decision.

### Slide 4 — Open the price, see the proof

**0:50–1:10 · 20 seconds**

Here is one real line: three hundred and ten square metres of insulation on page one hundred and thirteen. We can inspect the source, catalogue reference, and labour rule together.

### Slide 5 — Needs your decision

**1:10–1:30 · 20 seconds**

Page one hundred and ten includes a separate-tender note alongside installation obligations. The estimator resolves each position: include, installation only, or exclude. The decision gets a reason and a revision.

### Slide 6 — Compare the bid before committing

**1:30–1:45 · 15 seconds**

Aggressive, target, and conservative scenarios show the trade-offs before changes are accepted. The displayed win probabilities are illustrative assumptions, not reliable predictions.

### Slide 7 — What we measured

**1:45–2:20 · 35 seconds**

One local run created a draft in about fifty-five seconds, attempting all two hundred and two pages with one partial page. Separately, AI plus local fallbacks found eighty of eighty-three sampled rows and their explicit quantities and units. This is sampled extraction evidence, not pricing accuracy. Local checks also passed the twenty-two supplied examples.

### Slide 8 — Complete the handover

**2:20–2:30 · 10 seconds**

The handover carries source evidence, cost build-up, unresolved scope, and draft exports tied to a revision.

### Slide 9 — Prove value with estimators

**2:30–2:45 · 15 seconds**

Next, we propose testing five to ten historical tenders with estimators, measuring review time, corrections, and coverage. Real quotes and production features remain work to do.

### Slide 10 — Read the tender. See the gaps. Defend the price.

**2:45–3:00 · 15 seconds**

Read the tender. See the gaps. Defend the price. We are asking for an estimator partner and historical tenders to run that pilot. Thank you.

## Rehearsal

1. Practise the first two sentences and the final ask until you can say them without reading.
2. Speak slightly slower than everyday conversation. Aim for around 110–120 words per minute and use the remaining time for pauses and pointing.
3. Look at one judge for one full sentence, then change to another. A calm voice is more useful than a dramatic voice.
4. Keep a printed cue sheet with one cue per slide. If you lose your place, say the cue in your own words and continue.
5. Use only one clear pointer movement on each screenshot. Do not explain every button or read every number.
6. Record one full rehearsal. If it runs long, shorten the explanation of slide 6; keep the evidence caveats on slide 7.
7. When a judge asks a question, pause, answer the direct question in one sentence, then add one supporting fact.

## Pronunciation

| On the slide | Say it this way |
| --- | --- |
| BidGenius AI | Bid JEE-nee-us, A I |
| LA02 | L A zero two |
| P-INS-002 | P INS zero zero two |
| 310 m² | three hundred and ten square metres |
| 55.035 s | about fifty-five seconds |
| 80/83 | eighty out of eighty-three |
| CHF | Swiss francs |

## Demo fallback

Present the prepared screenshots. This keeps the five-minute talk independent of internet access or a live application.

**If the app is unavailable, say:** “These slides show the documented prepared run. I can still walk through the source, the calculation, and the decisions.”

If using the live workspace, rehearse the selected positions and visible totals first. It may now contain later edits and a different revision. Do not reset saved user work to force a match with the deck.

Do not call cached data a new extraction, describe local parsing as a live AI run, or imply that a draft export is an approved submission.
