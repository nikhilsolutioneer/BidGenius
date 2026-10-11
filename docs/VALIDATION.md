# Validation record — 10 October 2026

The delivered application was tested with the actual supplied Oberglatt package on this Windows laptop. The prepared run uses the **local parser**, with no model call or simulated progress. A separate isolated full-tender run is testing real OpenAI inference; it does not modify the prepared demo or earlier user projects.

## Automated checks

- **127 backend tests** cover the Decimal calculator, 22-position benchmark, parsing and matching, evaluator integrity, section batching, source validation, mocked OpenAI calls, transactional API mutations, proxy and AI proposal approval, historical imports, capacity/scenario revisioning, risk/opportunity approval, manual duplicate checks, undo, pinned exports, ZIP traversal rejection, one active process/run, scenario-reference warnings, and LangGraph SQLite restart/cancellation/retry behaviour.
- **Browser integration:** five checks cover actual PDF rendering, evidence selection, duplicate acknowledgement, manual recovery and reversal, quantity edit/recalculation/reversal, pending and approved risk behaviour, requirements review, proxy approval, historical CSV validation, capacity input, scenario persistence and export equality.
- **Visual and accessibility checks:** laptop, tablet and phone screenshots are in `frontend/test-artifacts/`. Automated axe checks cover the tested application views and dialogs. These checks supplement manual keyboard/focus/layout inspection; they are not a formal accessibility certification.
- Production frontend build and TypeScript checks pass. Dependency validation reports no broken Python requirements. Frontend npm audit reports zero known vulnerabilities at the time of testing.

The final full backend run passed **127 tests in 34.49 seconds**. Five browser checks passed, including an isolated README coverage workflow and existing workspace/accessibility checks; axe reported zero violations on the inspected views. The production frontend build and generated API types pass. Reproduce the backend suite with `.venv\Scripts\python.exe -m pytest -q`.

## Actual source extraction

`artifacts/evaluation.json` records the latest parser version, UTC timestamp, source/annotation hashes and row-level outcomes. The PDF-only evaluation took **35.999 seconds**.

| Check | Result |
|---|---:|
| Physical PDF pages attempted | 202 / 202 |
| Locally readable pages | 201 |
| Partial font mapping | Page 201 |
| Extracted position records | 715 |
| Unassigned candidate blocks | 11 |
| Supplied examples: detection, quantity/unit, reference, system | 22 / 22 each |
| Additional annotated rows: same checks | 29 / 29 each |

All five LA systems and rooftop supports appear. The extra 29 rows include 18 catalogue-matchable and 11 intentionally unmatched references. Those annotations were independently transcribed and subsequently used to fix parser defects; they are now a regression set, not untouched evidence of generalization. These measurements establish sampled recall and field correctness. They do not establish whole-tender extraction completeness, precision, technical equivalence, or a complete tender price.

## Calculator and commercial behaviour

The independent `benchmark_v1` calculation reproduces material **CHF 277,626.29**, labour **CHF 95,073.83**, direct cost **CHF 372,700.12**, and baseline **CHF 414,489.12** for the supplied 22-row subset. LV0001 reproduces CHF 388.96 material, 4.346875 hours, CHF 417.30 labour and CHF 806.26 direct cost. `500.225` hours displays as `500.23`.

The full workspace uses `full_draft_v1`. Both aggregation views reconcile to the same baseline, including project services, approved adjustments, overhead and disclosed display rounding. Pending opportunities do not reduce official totals. Invalid opportunities, duplicate allowance scope, stale edits and incompatible unit edits fail transactionally. A review-complete label remains blocked by unreviewed requirements, rejected positions, missing prices/quotes or unresolved evidence.

## Live OpenAI run

The isolated real-provider run used `gpt-4o`, completed all **202 / 202** pages and **53 / 53** batches, and persisted **740 positions** before entering estimator review. The server-recorded usage was **1,315,019 tokens** across **37 successful AI batches** and **16 validation fallbacks**; fallback batches retained deterministic local extraction and are visible in the run errors. The smoke request succeeded in 4.016 seconds. A restart/resume preserved 28 pages and seven completed batches. The final snapshot is in `artifacts/live-ai-verification.json`.

The frozen, purposive 83-row holdout measured **80 / 83 detection recall (96.39%)** and **80 / 83 explicit quantity/unit correctness (96.39%)**; among detected rows, quantity/unit correctness was **100%**. The previously unseen 81-row subset measured 78 detected and 78 quantity-unit-correct rows. This is source-anchored sampled evidence, not a claim of whole-tender extraction completeness, precision, technical equivalence, or pricing accuracy. Results are in `artifacts/live-holdout-evaluation.json`.

## Prepared run and measured latency

`artifacts/prepared-demo.json` contains the fresh project ID, UTC preparation timestamp, coverage, default commercial context, scenario reference comparison, financial values and ZIP export. The project remains at revision 1 with no estimator decision history.

| Measurement | Observed |
|---|---:|
| End-to-end 202-page import/extraction/draft | 55.035 s |
| Pages processed | 202 / 202 |
| Extracted positions | 679 |
| Priced positions | 137 |
| Unpriced positions | 542 |
| Additional model tokens in this run | 0 |

These are single-laptop observations, not performance guarantees. Validation was running on the same laptop. The 169 costed/included lines contain explicitly included package components; this is not a claim that 169 independently quoted products are complete. Known material/labour components can contribute to the included-scope price even when another component remains unresolved.

The clean prepared project's **indicative included-scope baseline is CHF 1,568,823.53**, with a reference selling price of **CHF 1,661,000** under the supplied prototype assumptions. **542 unpriced positions, 11 unresolved blocks, the partial page, unconfirmed quotations and missing drawings/Excel prevent a complete submission claim.**

The script created the ZIP export pinned to revision 1. Its contents are generated from that prepared project and include the estimate handover files; the archive was not independently unpacked during this preparation run.

## Explicit limitations

- Real OpenAI smoke and full-tender run progress are recorded in `artifacts/live-ai-verification.json`; the independent quantity/unit holdout is recorded in `artifacts/live-holdout-evaluation.json` after run completion. Results and batch fallbacks are reported separately from the local-parser benchmark.
- Local parsing is specialized for the supplied digital tender; OCR and drawing interpretation are outside scope.
- Catalogue coverage and installation rules are limited. Unknown amounts remain unresolved; assumptions require estimator review.
- Supplier prices are references, not confirmed quotes. Technical equivalence remains a separate decision.
- The prototype has no authentication, multiuser service or procurement submission. It listens on loopback.
- Scenario probabilities are uncalibrated supplied heuristics. No scenario is presented as statistically optimal.
