import { useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  Check,
  Download,
  FileArchive,
  FileJson,
  FileSpreadsheet,
  FileText,
  History as HistoryIcon,
  Info,
  Mail,
  Settings2,
  ShieldCheck,
  Undo2,
} from 'lucide-react';
import { Badge, Button, countOrDash, DetailRow, ErrorBox, Field, Modal, Spinner, Status } from './components';
import { date, label, money, number, post, probabilityPercent } from './api';
import type { History, Project, Scenarios, Summary, WhatIfPreview } from './types';
import type { Mutate } from './Dialogs';
import CommercialContext from './CommercialContext';
import HistoryChanges, { historyTarget } from './HistoryChanges';
import WhatIf from './WhatIf';
import { CurveWithPoints } from './charts/CurveWithPoints';
import { Tornado } from './charts/Tornado';
export function ScenarioPage({
  project,
  summary,
  mutate,
}: {
  project: Project;
  summary: Summary;
  mutate: Mutate;
}) {
  const [result, setResult] = useState<Scenarios | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [custom, setCustom] = useState(false);
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, unknown> | null>(null);
  const [saveReason, setSaveReason] = useState('');
  const [offerReason, setOfferReason] = useState('');
  const [live, setLive] = useState<{ preview: WhatIfPreview | null; loading: boolean; changed: boolean; margin: string }>({ preview: null, loading: false, changed: false, margin: String(project.parameters.commercial?.target_margin_pct ?? 5.5) });
  const [tool, setTool] = useState<'whatif' | 'sensitivity' | 'settings' | null>(null);
  const [offerScenario, setOfferScenario] = useState<Scenarios['scenarios'][number] | null>(null);
  const savedData = result || summary.scenarios;
  const previewScenarios = live.preview?.proposed.scenarios;
  const sortedPrices = previewScenarios && [...previewScenarios].sort((a, b) => Number(a.bid_price_chf) - Number(b.bid_price_chf));
  const data = previewScenarios?.length ? { ...savedData, scenarios: previewScenarios, low_chf: sortedPrices![0].bid_price_chf, high_chf: sortedPrices![sortedPrices!.length - 1].bid_price_chf, probability_curve: [...previewScenarios].sort((a, b) => Number(a.bid_price_chf) - Number(b.bid_price_chf)).map(s => ({ price_chf: s.bid_price_chf, estimated_win_probability: s.estimated_win_probability, achieved_margin_pct: s.achieved_margin_pct, expected_contribution_chf: s.expected_contribution_chf })) } : savedData;
  const defaults = {
    ...project.parameters.stretch_bid_optimization,
    ...((summary.scenarios.assumptions as Record<string, unknown>) || {}),
  };
  const historyControlsProbability = Boolean(summary.scenarios.commercial_evidence?.context?.adopt_observed_win_rate);
  const historyControlsReference = Boolean(summary.scenarios.commercial_evidence?.context?.adopt_reference_ratio);
  const margins = defaults.scenario_margins_pct as Record<string, number> | undefined;
  const referenceContext = data?.reference_context || summary.scenario_reference;
  const modelAssumptions = (data?.assumptions || summary.scenarios.assumptions || {}) as Record<string, unknown>;
  const closestScenario = data?.scenarios?.reduce((closest, candidate) =>
    Math.abs(Number(candidate.bid_price_chf) - Number(summary.totals.selling_price_chf)) < Math.abs(Number(closest.bid_price_chf) - Number(summary.totals.selling_price_chf)) ? candidate : closest,
  );
  return (
    <div className="page-content scenario-page scenario-workspace scenario-live-workspace">
      <div className="page-heading">
        <div>
          <div className="eyebrow">COMMERCIAL PERSPECTIVE</div>
          <h1>A range. With a reason.</h1>
          <p>Explore the price of included scope under explicit commercial assumptions.</p>
        </div>
        <div className="scenario-heading-summary"><span><small>RECOMMENDED BID RANGE</small><strong>{money(data?.low_chf)}–{money(data?.high_chf)}</strong></span><Badge tone="blue">Revision {summary.revision}</Badge></div>
      </div>
      <div className="scenario-reconciliation">Indicative price (target margin {number(project.parameters.commercial?.target_margin_pct ?? 5.5, 1)}%, project_parameters.commercial) {money(summary.totals.selling_price_chf)} · Scenario margins from project_parameters.stretch_bid_optimization: Aggressive 2.5% / Target 4.0% / Conservative 6.5%</div>
      <Modal open={tool === 'sensitivity'} onClose={() => setTool(null)} title="Which assumption moves the price?" description="Compare price sensitivity, then select an assumption to explore its impact." wide>
      <section className="scenario-tool-body scenario-tornado">
        <div className="panel-header"><h2>Which assumption moves the price?</h2></div>
        <Tornado projectId={project.id} revision={summary.revision} onOpenControl={(field) => { setTool(null); requestAnimationFrame(() => { const control = document.getElementById(`whatif-${field}`); const disclosure = control?.closest('details'); if (disclosure) disclosure.open = true; control?.focus(); }); }} />
      </section>
      </Modal>
      <aside className="scenario-live-controls" aria-label="Live assumptions">
        <div className="scenario-controls-title"><h2>Adjust assumptions</h2><p>Move a slider. Compare all three strategies live.</p></div>
        <WhatIf projectId={project.id} summary={summary} mutate={mutate} onPreviewChange={setLive} />
      </aside>
      <div className="scenario-overview-row">
      <section className="panel scenario-curve">
        <div className="panel-header"><h2>Price vs illustrative win probability</h2></div>
        <CurveWithPoints curve={data?.probability_curve || []} scenarios={data?.scenarios || []} selected={closestScenario?.scenario} />
      </section>
      <section className="scenario-current-price">
        <span className="eyebrow">{live.loading ? 'RECALCULATING…' : live.preview ? 'PREVIEWED SELLING PRICE' : 'CURRENT SELLING PRICE'}</span><strong aria-live="polite">{money(live.preview?.proposed.selling_price_chf ?? summary.totals.selling_price_chf)}</strong>
        <span>{live.preview ? 'Unsaved preview' : 'Saved offer'} · {number(live.preview ? live.margin : project.parameters.commercial?.target_margin_pct ?? 5.5, 1)}% target margin · Revision {summary.revision}</span>
        {live.preview && <small>Saved price {money(summary.totals.selling_price_chf)} · change {Number(live.preview.deltas.selling_price_chf) > 0 ? '+' : ''}{money(live.preview.deltas.selling_price_chf)}</small>}
        <div><small>Scenario bid range · margins shown below</small><b>{money(data?.low_chf)} – {money(data?.high_chf)}</b></div>
        <small>{live.changed ? 'Apply or reset the preview using the controls on the left.' : 'Use the controls on the left to preview a change.'}</small>
        <small>Included scope only. {summary.coverage.positions_unpriced} positions remain unpriced.</small>
      </section>
      </div>
      <div className="scenario-hero">
        <div>
          <div className="section-label">RECOMMENDED BID RANGE FOR INCLUDED SCOPE</div>
          <div className="range-price">
            {money(data?.low_chf)} <span>–</span> {money(data?.high_chf)}
          </div>
          <small>Scenario range · scenario margin assumptions shown on each offer price</small>
          <p>
            Based on a cost baseline of <strong>{money(summary.totals.cost_baseline_chf, 2)}</strong>. Bid
            range based on assumptions, for included scope. Excludes unresolved and unpriced scope.
          </p>
          <p>Saved indicative price at revision {summary.revision}: <strong>{money(summary.totals.selling_price_chf, 2)}</strong>. {summary.coverage.provisional_priced_positions} supplier reference prices ({money(summary.coverage.provisional_direct_cost_chf, 2)} direct) await quotes.</p>
        </div>
        <BarChart3 size={64} strokeWidth={1.2} />
      </div>
      <div className="note scenario-note">
        <Info size={19} />
        <div>
          <strong>Illustrative scenario model</strong>
          <p>
            Probabilities are illustrative, not calibrated predictions. Historical records affect results only
            after explicit adoption below. These scenarios support estimator judgment; they do not identify an
            optimal bid.
          </p>
        </div>
      </div>
      {referenceContext?.defaults_available && (
        <section className="scenario-reference" aria-label="Win probability model reference">
          <div>
            <span>REFERENCE PRICE</span>
            <strong>{money(modelAssumptions.reference_price_chf, 2)}</strong>
            <small>project_parameters.json default · baseline ÷ (1 − margin): {money(referenceContext.default_reference_price_chf, 2)}</small>
          </div>
          <div>
            <span>REFERENCE MARGIN</span>
            <strong>{number(modelAssumptions.reference_margin_pct, 1)}%</strong>
            <small>project_parameters.json default: {number(referenceContext.default_reference_margin_pct, 1)}%</small>
          </div>
          {(referenceContext.reference_margin_differs_from_default || referenceContext.reference_price_differs_from_default) && (
            <div className="scenario-reference-warning" role="status">
              <Info size={16} />
              <span>
                {referenceContext.reference_margin_differs_from_default && (
                  <>Reference margin overridden: {number(modelAssumptions.reference_margin_pct, 1)}% (default {number(referenceContext.default_reference_margin_pct, 1)}%).</>
                )}
                {referenceContext.reference_margin_differs_from_default && referenceContext.reference_price_differs_from_default && ' '}
                {referenceContext.reference_price_differs_from_default && (
                  <>Reference price differs from the package default: {money(modelAssumptions.reference_price_chf, 2)} vs {money(referenceContext.default_reference_price_chf, 2)}.</>
                )}
              </span>
            </div>
          )}
        </section>
      )}
      <div className="scenario-grid">
        {data?.scenarios?.map((s, i) => (
          <section className={`panel scenario-card scenario-${i}`} key={s.scenario}>
            <div className="scenario-name">
              <span className="scenario-dot" />
              <h2>{s.scenario}</h2>
              {(custom || live.preview) && <Badge tone="blue">Unsaved preview</Badge>}
              {closestScenario?.scenario === s.scenario && <Badge tone="green">Closest to saved indicative price</Badge>}
            </div>
            <div className="scenario-price">{money(s.bid_price_chf)}</div>
            <p className="scenario-margin-note">Offer price · {number(s.margin_pct)}% margin</p>
            <DetailRow name="Requested margin">{number(s.margin_pct)}%</DetailRow>
            <DetailRow name="Achieved margin">{number(s.achieved_margin_pct)}%</DetailRow>
            <div className="probability">
              <div>
                <span>Illustrative win probability</span>
                <strong>{probabilityPercent(s.estimated_win_probability)}%</strong>
              </div>
              <div className="progress-track">
                <div style={{ width: `${probabilityPercent(s.estimated_win_probability)}%` }} />
              </div>
            </div>
            <div className="contribution">
              <span>Expected contribution</span>
              <strong>{money(s.expected_contribution_chf)}</strong>
            </div>
            <p className="scenario-why">
              <strong>Why this recommendation</strong>
              <span>
                {s.price_vs_reference_pct === null
                  ? 'Price vs reference unavailable; '
                  : `Offer is ${s.price_vs_reference_pct.startsWith('-') ? '' : '+'}${number(s.price_vs_reference_pct, 1)}% vs reference; `}
                achieved margin {number(s.achieved_margin_pct, 1)}%, illustrative win probability {probabilityPercent(s.estimated_win_probability)}%,
                {' '}expected contribution {money(s.expected_contribution_chf)}.
              </span>
            </p>
            <Button disabled={live.changed || live.loading} onClick={() => { setOfferReason(''); setOfferScenario(s); }}>Use as offer price <ArrowRight size={14} /></Button>
          </section>
        ))}
      </div>
      <div className="scenario-tools-row">
        <Button onClick={() => setTool('sensitivity')}><BarChart3 size={18} /> Price sensitivity <ArrowRight size={14} /></Button>
        <Button onClick={() => setTool('settings')}><Settings2 size={18} /> Scenario assumptions · Commercial context <ArrowRight size={14} /></Button>
        <span>Win probabilities are illustrative, not calibrated predictions.</span>
      </div>
      <Modal open={offerScenario !== null} onClose={() => setOfferScenario(null)} title="Use as offer price" description={`${offerScenario?.scenario || ''} · ${money(offerScenario?.bid_price_chf)} · ${offerScenario?.margin_pct || ''}% target margin`}>
        <div className="modal-body"><Field label="Reason to use this offer price"><input value={offerReason} onChange={event => setOfferReason(event.target.value)} /></Field>{error && <p role="alert">{error}</p>}</div>
        <div className="modal-footer"><Button disabled={busy || offerReason.trim().length < 3} variant="primary" onClick={async () => {
          if (!offerScenario) return;
          setBusy(true); setError('');
          try { await mutate(`/projects/${project.id}/assumptions`, { reason: offerReason.trim(), changes: { commercial: { target_margin_pct: offerScenario.margin_pct } } }); setOfferScenario(null); }
          catch (caught) { setError((caught as Error).message); }
          finally { setBusy(false); }
        }}>Confirm offer price</Button></div>
      </Modal>
      <Modal open={tool === 'settings'} onClose={() => setTool(null)} title="Scenario assumptions & commercial context" description="Review the model inputs and evidence. Changes require a reason before saving." wide>
      <div className="scenario-tool-body">
      <section className="panel scenario-inputs">
        <div className="panel-header">
          <div>
            <h2>
              <Settings2 size={18} /> Scenario assumptions
            </h2>
            <p>
              Preview assumptions, then save a revision so the displayed scenarios and exported estimate
              agree.
            </p>
          </div>
          {custom && (
            <Button
              variant="ghost"
              onClick={() => {
                setResult(null);
                setCustom(false);
                setPendingOverrides(null);
              }}
            >
              Restore saved scenarios
            </Button>
          )}
        </div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            const f = new FormData(e.currentTarget);
            const scenario_margins_pct: Record<string, string> = {};
            for (const name of ['Aggressive', 'Target', 'Conservative'])
              scenario_margins_pct[name] = String(f.get(name));
            try {
              const overrides: Record<string, unknown> = {
                scenario_margins_pct,
                reference_margin_pct: String(f.get('reference_margin')),
                reference_win_probability: String(f.get('probability')),
                price_sensitivity_probability_points_per_1pct_price: String(f.get('sensitivity')),
                strategic_appetite_adjustment: String(f.get('appetite')),
                competition_adjustment: String(f.get('competition')),
              };
              if (historyControlsProbability) delete overrides.reference_win_probability;
              if (historyControlsReference) delete overrides.reference_margin_pct;
              setResult(
                await post<Scenarios>(`/projects/${project.id}/scenarios`, {
                  revision: summary.revision,
                  overrides,
                }),
              );
              setPendingOverrides(overrides);
              setCustom(true);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="panel-body">
            {error && <ErrorBox message={error} />}
            {(historyControlsProbability || historyControlsReference) && <div className="note">Approved historical evidence controls {historyControlsProbability ? "the reference probability" : ""}{historyControlsProbability && historyControlsReference ? " and " : ""}{historyControlsReference ? "the reference price" : ""}. Change the adoption settings below to return to manual assumptions.</div>}
            <div className="form-grid three">
              {['Aggressive', 'Target', 'Conservative'].map((name, i) => (
                <Field label={`${name} margin · %`} key={name}>
                  <input
                    name={name}
                    type="number"
                    min="0"
                    max="99.9"
                    step="0.1"
                    defaultValue={margins?.[name] ?? [2.5, 4, 6.5][i]}
                    required
                  />
                </Field>
              ))}
            </div>
            <div className="form-grid">
              <Field
                label="Reference margin (%)"
                hint="Defines the reference price used to compare scenario bids."
              >
                <input
                  name="reference_margin"
                  readOnly={historyControlsReference}
                  type="number"
                  min="0"
                  max="99.9"
                  step="0.1"
                  defaultValue={String(defaults.reference_margin_pct ?? 5.5)}
                  required
                />
              </Field>
              <Field label="Reference win probability" hint="A probability from 0 to 1, not a percentage.">
                <input
                  name="probability"
                  readOnly={historyControlsProbability}
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  defaultValue={String(defaults.reference_win_probability ?? '.55')}
                  required
                />
              </Field>
              <Field label="Price sensitivity" hint="Probability points per 1% relative price difference.">
                <input
                  name="sensitivity"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  defaultValue={String(defaults.price_sensitivity_probability_points_per_1pct_price ?? '.05')}
                  required
                />
              </Field>
              <Field label="Strategic appetite adjustment">
                <input
                  name="appetite"
                  type="number"
                  min="-1"
                  max="1"
                  step="0.01"
                  defaultValue={String(defaults.strategic_appetite_adjustment ?? '.05')}
                  required
                />
              </Field>
              <Field label="Competition adjustment">
                <input
                  name="competition"
                  type="number"
                  min="-1"
                  max="1"
                  step="0.01"
                  defaultValue={String(defaults.competition_adjustment ?? '-.05')}
                  required
                />
              </Field>
            </div>
            <div className="form-bottom">
              <span className="text-muted">All financial results are calculated by the backend.</span>
              <Button variant="primary" type="submit" disabled={busy}>
                {busy ? 'Calculating…' : 'Recalculate scenarios'}
                <ArrowRight size={15} />
              </Button>
            </div>
          </div>
        </form>
        {custom && pendingOverrides && (
          <div className="panel-body scenario-save">
            <div className="note">
              Unsaved preview. Exports still use revision {summary.revision}. Save these assumptions to
              include this scenario comparison in the handover.
            </div>
            <Field label="Scenario change reason">
              <input
                value={saveReason}
                onChange={(e) => setSaveReason(e.target.value)}
                placeholder="Commercial basis for these assumptions"
              />
            </Field>
            <Button
              variant="primary"
              disabled={busy || !saveReason.trim()}
              onClick={async () => {
                setBusy(true);
                setError('');
                try {
                  await mutate(
                    `/projects/${project.id}/scenarios/save`,
                    { reason: saveReason, overrides: pendingOverrides },
                    'POST',
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? 'Saving?' : 'Save scenarios to revision'}
            </Button>
          </div>
        )}
      </section>
      <CommercialContext projectId={project.id} mutate={mutate} />
      </div>
      </Modal>
      <div className="note">
        <Info size={16} />
        {summary.coverage.positions_unpriced} positions remain unpriced and {summary.coverage.pending_reviews}{' '}
        reviews are pending. The interval covers included scope only.
      </div>
    </div>
  );
}
export function ExportPage({
  project,
  summary,
  onUndo,
}: {
  project: Project;
  summary: Summary;
  onUndo: (h: History) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [downloads, setDownloads] = useState<{ url: string; filename: string }[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const formats = [
    {
      key: 'zip',
      title: 'Complete review package',
      description: 'Estimate, evidence, assumptions, and supplier questions in one archive.',
      icon: FileArchive,
      featured: true,
    },
    {
      key: 'html',
      title: 'Draft offer · German',
      description: 'Print-ready estimate with unresolved scope and source references.',
      icon: FileText,
    },
    {
      key: 'csv',
      title: 'Position spreadsheet',
      description: 'Structured positions, costs, quantities, and review outcomes.',
      icon: FileSpreadsheet,
    },
    {
      key: 'json',
      title: 'Calculation & evidence',
      description: 'Machine-readable revision, calculation inputs, and audit evidence.',
      icon: FileJson,
    },
    {
      key: 'rfq',
      title: 'Supplier RFQ drafts',
      description: 'Outstanding quantities, specifications, and quotation questions.',
      icon: Mail,
    },
  ];
  const generate = async (format: string) => {
    setBusy(format);
    setError('');
    try {
      const result = await post<{ url: string; filename: string }>(`/projects/${project.id}/exports`, {
        revision: summary.revision,
        format,
      });
      setDownloads((ds) => [result, ...ds]);
      const a = document.createElement('a');
      a.href = result.url;
      a.download = result.filename;
      if (format === 'html') {
        a.target = '_blank';
        a.rel = 'noreferrer';
      }
      a.click();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="page-content export-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">ESTIMATE HANDOVER</div>
          <h1>The price. And the proof.</h1>
          <p>Export a pinned revision with the reasoning that belongs to it.</p>
        </div>
        <div className="export-heading-actions">
          <Badge tone="blue">Revision {summary.revision}</Badge>
          <button
            type="button"
            className="export-history-trigger"
            aria-label="Decision history"
            title="Decision history"
            aria-haspopup="dialog"
            onClick={() => setHistoryOpen(true)}
          >
            <HistoryIcon size={20} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="export-status panel">
        <div className="export-status-icon">
          <ShieldCheck size={27} />
        </div>
        <div>
          <h2>
            {summary.review_complete
              ? 'Review complete for included scope'
              : 'Draft estimate — review outstanding'}
          </h2>
          <p>
            {summary.completeness ? (
              <>
                {summary.completeness.pct_positions_priced !== null && summary.completeness.pct_positions_priced !== undefined && <><strong>{countOrDash(summary.completeness.pct_positions_priced)}% of positions priced</strong> ·{' '}</>}
                {countOrDash(summary.coverage.positions_priced)} priced / {countOrDash(summary.coverage.positions_included_elsewhere)} covered elsewhere / {countOrDash(summary.coverage.positions_unpriced)} unpriced ·{' '}
                Unpriced scope allowance: {money(summary.completeness.allowance_low_chf)}–{money(summary.completeness.allowance_high_chf)} ({summary.completeness.positions_no_basis} rows lack a benchmark; not included)
              </>
            ) : (
              <>
                {summary.coverage.positions_unpriced} unpriced positions · {summary.coverage.pending_reviews}{' '}
                pending reviews · {summary.coverage.pages_processed}/{summary.coverage.total_pages} pages processed
              </>
            )}
          </p>
        </div>
        <div className="export-total">
          <small>INDICATIVE PRICE</small>
          <strong>{money(summary.totals.selling_price_chf)}</strong>
          <small>Cost baseline {money(summary.totals.cost_baseline_chf, 2)}</small>
        </div>
      </div>
      <div className="note">
        <Info size={16} />
        Every export carries its revision, priced scope completeness, unpriced scope benchmark allowance, and draft status. Exporting does not mark the
        estimate as reviewed.
      </div>
      {error && <ErrorBox message={error} />}
      <div className="export-grid">
        {formats.map((f) => (
          <section className={`panel export-card ${f.featured ? 'export-featured' : ''}`} key={f.key}>
            <div className="export-format-icon">
              <f.icon size={24} />
            </div>
            <div>
              {f.featured && <div className="eyebrow">RECOMMENDED HANDOVER</div>}
              <h2>{f.title}</h2>
              <p>{f.description}</p>
            </div>
            <Button
              variant={f.featured ? 'primary' : 'default'}
              disabled={busy !== null}
              onClick={() => void generate(f.key)}
            >
              {busy === f.key ? 'Preparing…' : f.key === 'html' ? 'Open printable draft' : 'Download'}
              <Download size={15} />
            </Button>
          </section>
        ))}
      </div>
      {busy && <Spinner text="Preparing an immutable revision export…" />}
      {downloads.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <h2>
              <Check size={17} /> Prepared downloads
            </h2>
          </div>
          <div className="download-list">
            {downloads.map((d, i) => (
              <a key={`${d.url}-${i}`} href={d.url} download={d.filename}>
                <FileText size={15} />
                {d.filename}
                <Download size={15} />
              </a>
            ))}
          </div>
        </section>
      )}
      <Modal
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title="Decision history"
        description="Every change has an owner, a reason, and a financial effect."
        wide
      >
        <div className="modal-body export-history-dialog">
        {summary.history.length === 0 ? (
          <div className="register-empty">
            <HistoryIcon size={24} />
            <p>No estimator changes have been recorded for this project yet.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table history-table">
              <thead>
                <tr>
                  <th>Revision / date</th>
                  <th>Decision</th>
                  <th>Price change</th>
                  <th>Actor</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {summary.history
                  .slice()
                  .reverse()
                  .map((h) => (
                    <tr key={h.id}>
                      <td>
                        <Badge tone="blue">Rev {h.revision}</Badge>
                        <small>{date(h.timestamp)}</small>
                      </td>
                      <td>
                        <strong>{h.reason}</strong>
                        <small>
                          {label(h.entity_type)} · {historyTarget(h)}
                        </small>
                        <details>
                          <summary>Inspect values</summary>
                          <HistoryChanges decision={h} />
                        </details>
                      </td>
                      <td className="numeric">{money(h.price_delta_chf, 2)}</td>
                      <td>{h.actor}</td>
                      <td>
                        <Button variant="ghost" onClick={() => onUndo(h)}>
                          <Undo2 size={14} /> Reverse
                        </Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
        </div>
      </Modal>
      <section className="panel">
        <div className="panel-header">
          <h2>Scope ownership and assumptions</h2>
        </div>
        <div className="panel-body">
          <details>
            <summary>Scope ownership · {(summary.scope_allocations as unknown[]).length} entries</summary>
            <div className="audit-list">
              {(summary.scope_allocations as { scope: string; owner: string; amount_chf: string; position_ids: string[]; basis: string }[]).map((entry, index) => (
                <div key={index}>
                  <strong>{label(entry.scope)} → {label(entry.owner.replace('project:', ''))}</strong>
                  <span>{entry.position_ids.length} linked position{entry.position_ids.length === 1 ? '' : 's'} · {entry.amount_chf === '0.00' ? 'Charged to owner' : money(entry.amount_chf, 2)} · {entry.basis}</span>
                </div>
              ))}
            </div>
          </details>
          <details>
            <summary>Calculation assumptions · {(summary.assumptions as unknown[]).length} entries</summary>
            <div className="audit-list">
              {(summary.assumptions as { text?: string }[]).map((entry, index) => <div key={index}>{entry.text || 'Recorded project assumption'}</div>)}
            </div>
          </details>
          <div className="inline">
            <Status status={summary.review_complete ? 'accepted' : 'pending'} />
            <span className="text-muted">Formal procurement submission is outside this prototype.</span>
          </div>
        </div>
      </section>
    </div>
  );
}
