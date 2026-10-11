# Shared integration contract

Python package: `backend/tenderproof`. Shared Pydantic types: `models.py` (coordinator-owned). JSON financial values are decimal strings. Root service/API owns SQLite, LangGraph execution, revisions and exports. Original starter files are read-only and evaluation examples MUST NOT be used by production extraction.

## Ingestion agent interface

Implement `ingestion.py`, `matching.py`, `ai.py`, `prompts.py` and associated tests. Own only these modules and your tests. Import shared types.

- `parse_pdf(path: Path, document_id: str, progress: Callable | None = None) -> tuple[list[PageRecord], list[SourceSpan]]`: parse every page, stable IDs, coordinates, inherited system, truthful statuses. `progress(page_number, total_pages)` optional.
- `extract_local_batch(pages: list[PageRecord], spans: list[SourceSpan], catalog: list[dict]) -> ExtractionBatch`: deterministic extraction independent of examples. Receives up to4 current pages plus optional previous-page context supplied separately only if needed. A robust local parser is essential for use without an API key.
- `match_position(position: Position, catalog: list[dict]) -> Position`: match + explicit constraints, normalized attrs and confidence. Preserve overrides and warnings. Return new model.
- `async extract_ai_batch(pages: list[PageRecord], spans: list[SourceSpan], catalog: list[dict], model: str) -> ExtractionBatch`: official OpenAI Responses structured outputs, source validation, bounded retries, `store=False`. Uses env key. Errors must be explicit, caller may retain local results marked fallback.

You can add helper functions but do not change the above without messaging coordinator. Requirements/issues cite source IDs. `PageRecord.system` canonical `LA01`..`LA05`, `ROOF`, or `Unassigned`; map based on actual section evidence, not global hardcoded page assumptions for arbitrary inputs. `Position.attributes` can carry dimensions/conversions/inclusions. Use `scope_tags` for supplied_by_others, commissioning, documentation, hygiene, transport, engineering. Service rows covered by project allowances set `included_in` to `project:commissioning` etc, pricing_basis included_elsewhere with explicit assumption. Unknown amounts remain null. For pricing use product_id and install_code.

## Pricing agent interface

Implement `pricing.py`, `reference.py`, tests/test_pricing.py and benchmark CLI `benchmark.py`. Import shared models.

- `load_reference(package: Path) -> dict` returning `catalog: list[dict], productivity: list[dict], parameters: dict`; strings for CSV numbers.
- `price_position(position: Position, catalog: list[dict], productivity: list[dict], parameters: dict, policy: str='full_draft_v1') -> Position` returns with CostLine; unknown remains null. Use overrides: net_unit_cost_chf, hourly_rate_chf, material_waste_pct, factor_overrides dictionary, install_code. Invalid input ValueError.
- `calculate_estimate(positions: list[Position], catalog: list[dict], productivity: list[dict], parameters: dict, adjustments: list[CommercialAdjustment] | None=None, policy: str='full_draft_v1') -> dict` returns `positions` list serialized, `totals` dictionary, `build_up` list, `by_system` list, `by_category` list, `scope_allocations` list, `assumptions` list, `scenarios` dictionary. Common totals: material_cost_chf, labour_cost_chf, direct_cost_chf, cost_baseline_chf, selling_price_chf, installation_hours, risk_adjustments_chf, opportunity_adjustments_chf, pending_adjustment_delta_chf. Build_up entries: key,label,amount_chf,formula,basis. Aggregation entries: key,label,material_cost_chf,labour_cost_chf,amount_chf,positions,unpriced. Summary grand totals should reconcile to baseline (price separate). Return any additional explicit totals needed. Each priced position uses full-precision unrounded components. Reconcile displayed bucket residual on project-level explicitly if needed.
- `calculate_scenarios(baseline: str, parameters: dict, overrides: dict | None=None) -> dict` returns scenarios array (scenario,bid_price_chf,margin_pct,achieved_margin_pct,estimated_win_probability,expected_contribution_chf), low_chf,high_chf,assumptions,label.

## Frontend API

GET /api/health -> {status,version,ai_configured,model}
GET /api/projects -> list {id,name,revision,created_at,updated_at,document,latest_run}
POST /api/projects/demo body {use_ai:false} -> {project_id,run_id}; starts actual PDF run. After first demo use GET projects to reopen.
POST /api/projects/import multipart files -> {project_id,run_id}; local run by default.
GET /api/projects/{id} -> {id,name,revision,document,parameters,latest_run,created_at,updated_at}
POST /api/projects/{id}/runs {use_ai:false} -> {run_id,project_id}
GET /api/runs/{id} -> Run
POST /api/runs/{id}/resume {expected_revision,reason,action:'continue'|'complete_review'}
POST /api/runs/{id}/cancel
GET /api/projects/{id}/positions -> {items:Position[],total,revision}; optional search/system/status/needs_review query
GET /api/projects/{id}/summary -> {project_id,revision,name,document,totals,build_up,by_system,by_category,coverage,issues,requirements,adjustments,assumptions,scope_allocations,scenarios,latest_run,review_complete,history}. coverage fields: pages_processed,total_pages,positions_extracted,positions_manual,positions_priced,positions_unpriced,pending_reviews,unassigned_blocks,failed_pages. All monetary strings.
GET /api/projects/{id}/references -> {catalog,productivity,parameters}
PATCH /api/positions/{id} {expected_revision,reason,changes:{quantity,unit,product_id,system,category,review_state,technical_equivalence,overrides,...}} -> {revision,price_delta_chf,position}
POST /api/projects/{id}/positions ManualPositionCreate -> same mutation envelope
PATCH /api/projects/{id}/assumptions {expected_revision,reason,changes:{productivity_factors:{...},allowances:{...},commercial:{...},project_costs:{...}}}
POST /api/projects/{id}/adjustments AdjustmentCreate -> {revision,adjustment,price_delta_chf}
PATCH /api/adjustments/{id} AdjustmentPatch -> same
POST /api/projects/{id}/undo/{decision_id} {expected_revision,reason} -> mutation envelope
PATCH /api/projects/{id}/issues/{issue_id} {expected_revision,reason,changes:{review_state:'accepted'}}
GET /api/documents/{id}/file -> PDF
GET /api/documents/{id}/pages/{page}/spans -> {items:SourceSpan[],page,width,height}
GET /api/sources/{id} -> SourceSpan
POST /api/projects/{id}/scenarios {revision,overrides:{scenario_margins_pct:{...},reference_win_probability,...}} -> scenarios
POST /api/projects/{id}/exports {revision,format:'csv'|'json'|'html'|'rfq'|'zip'} -> {url,filename}; GET returned URL downloads artifact (html supports print)

Errors: {detail:string | {message:string,duplicates?:Position[]}}. 409 stale revision or duplicate. UI always sends current project revision and refreshes after mutations. Money display uses Intl.NumberFormat de-CH currencyCHF, authoritative math remains backend. App must show local parsing vs AI mode honestly.
