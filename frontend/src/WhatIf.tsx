import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownRight, ArrowRight, ArrowUpRight, Clock3, LoaderCircle, RotateCcw, SlidersHorizontal, Sparkles } from 'lucide-react';
import { ApiError, money, number, post } from './api';
import { Badge } from './components';
import type { Mutate } from './Dialogs';
import type { Summary, WhatIfPreview } from './types';

type Draft = {
  productivity_factors: Record<string, string>;
  allowances: Record<string, string>;
  commercial: Record<string, string>;
  labour_rates_chf_per_h: Record<string, string>;
};

const factorLabels: Record<string, string> = {
  site_efficiency: 'Site efficiency',
  mounting_height_school: 'Mounting height · school',
  mounting_height_sports_hall: 'Mounting height · sports hall',
  school_logistics: 'School logistics',
  timber_interface: 'Timber interface',
};
const factorHints: Record<string, string> = {
  site_efficiency: 'Base installation hours ÷ this factor · project parameters',
  mounting_height_school: 'Multiplies hours only where the productivity rule applies it',
  mounting_height_sports_hall: 'Multiplies hours for applicable sports hall positions',
  school_logistics: 'Multiplies hours only where the productivity rule applies it',
  timber_interface: 'Multiplies hours only where the productivity rule applies it',
};

function stringValues(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item ?? '')]));
}

function draftFrom(summary: Summary): Draft {
  const parameters = summary.parameters || {};
  const factors = stringValues(parameters.productivity_factors);
  const allowances = stringValues(parameters.allowances);
  const commercial = stringValues(parameters.commercial);
  const rates = stringValues(parameters.labour_rates_chf_per_h);
  return {
    productivity_factors: Object.fromEntries(Object.keys(factorLabels).filter((key) => factors[key] !== undefined).map((key) => [key, factors[key]])),
    allowances: { material_waste_pct: allowances.material_waste_pct ?? '0' },
    commercial: {
      overhead_pct: commercial.overhead_pct ?? '0',
      target_margin_pct: commercial.target_margin_pct ?? '0',
    },
    labour_rates_chf_per_h: rates,
  };
}

function changesFrom(draft: Draft) {
  return Object.fromEntries(
    (Object.entries(draft) as [keyof Draft, Record<string, string>][]).filter(([, values]) => Object.keys(values).length > 0),
  );
}

function signedMoney(value: string) {
  if (value === '0' || value === '0.00') return '±CHF 0 · unchanged';
  return `${value.startsWith('-') ? '−' : '+'}${money(value.startsWith('-') ? value.slice(1) : value, 0)}`;
}

function signedHours(value: string) {
  if (value === '0' || value === '0.0') return '±0 h · unchanged';
  return `${value.startsWith('-') ? '−' : '+'}${number(value.startsWith('-') ? value.slice(1) : value, 3)} h`;
}

function signedPercent(value: string | null) {
  if (value === null) return '—';
  if (value === '0' || value === '0.0') return '0.0%';
  return `${value.startsWith('-') ? '−' : '+'}${value.startsWith('-') ? value.slice(1) : value}%`;
}

function RangeControl({
  id,
  label,
  value,
  min,
  max,
  step,
  suffix = '',
  hint,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  min: string;
  max: string;
  step: string;
  suffix?: string;
  hint: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="whatif-control">
      <div className="whatif-control-heading">
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id}>{value}{suffix}</output>
      </div>
      <input
        id={id}
        aria-label={label}
        aria-valuetext={`${value}${suffix}`}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
      <small>{hint}</small>
    </div>
  );
}

export default function WhatIf({
  projectId,
  summary,
  mutate,
  onPreviewChange,
}: {
  projectId: string;
  summary: Summary;
  mutate: Mutate;
  onPreviewChange?: (state: { preview: WhatIfPreview | null; loading: boolean; changed: boolean; margin: string }) => void;
}) {
  const baseline = useMemo(() => draftFrom(summary), [projectId, summary.revision]);
  const [draft, setDraft] = useState(baseline);
  const [preview, setPreview] = useState<WhatIfPreview | null>(null);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const changed = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => {
    onPreviewChange?.({ preview, loading, changed, margin: draft.commercial.target_margin_pct });
  }, [preview, loading, changed, draft.commercial.target_margin_pct, onPreviewChange]);

  useEffect(() => {
    setDraft(baseline);
    setPreview(null);
    setReason('');
    setError('');
  }, [summary.revision, projectId]);

  useEffect(() => {
    const requestSequence = ++sequence.current;
    if (!changed) {
      setPreview(null);
      setLoading(false);
      setError('');
      return;
    }
    setPreview(null);
    setLoading(true);
    setError('');
    const timer = window.setTimeout(async () => {
      try {
        const result = await post<WhatIfPreview>(`/projects/${projectId}/what-if/preview`, {
          expected_revision: summary.revision,
          changes: changesFrom(draft),
        });
        if (sequence.current === requestSequence) setPreview(result);
      } catch (caught) {
        if (sequence.current === requestSequence) {
          setError(caught instanceof ApiError && caught.status === 409
            ? 'This estimate has a newer revision. Refresh the page before applying this preview.'
            : (caught as Error).message);
        }
      } finally {
        if (sequence.current === requestSequence) setLoading(false);
      }
    }, 220);
    return () => {
      window.clearTimeout(timer);
      if (sequence.current === requestSequence) sequence.current += 1;
    };
  }, [changed, draft, projectId, summary.revision]);

  const setField = (group: keyof Draft, key: string, value: string) => {
    setDraft((current) => ({ ...current, [group]: { ...current[group], [key]: value } }));
  };

  const reset = () => {
    setDraft(baseline);
    setPreview(null);
    setReason('');
    setError('');
  };

  const apply = async () => {
    if (!preview || preview.revision !== summary.revision || reason.trim().length < 3) return;
    setApplying(true);
    setError('');
    try {
      await mutate(`/projects/${projectId}/assumptions`, {
        reason: reason.trim(),
        changes: changesFrom(draft),
      });
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setApplying(false);
    }
  };

  return (
    <section className="whatif-panel panel" aria-labelledby="whatif-title">
      <header className="whatif-header">
        <div className="whatif-title-wrap">
          <span className="whatif-icon"><SlidersHorizontal size={19} /></span>
          <div>
            <div className="eyebrow">LIVE ESTIMATE · REVISION {summary.revision}</div>
            <h2 id="whatif-title">What changes when you adjust the plan?</h2>
            <p>Move a control. See the offer recalculate against this revision before you save anything.</p>
          </div>
        </div>
        <Badge tone={preview ? 'green' : 'blue'}>{preview ? 'Preview ready' : 'No pending preview'}</Badge>
      </header>

      <div className="whatif-layout">
        <div className="whatif-controls">
          <details open className="whatif-control-disclosure">
            <summary>Site productivity</summary>
          <div className="whatif-control-group">
            {Object.entries(factorLabels).filter(([key]) => draft.productivity_factors[key] !== undefined).map(([key, text]) => (
              <RangeControl key={key} id={`whatif-${key}`} label={text}
                value={draft.productivity_factors[key]} min="0.50" max="1.50" step="0.01" suffix="×"
                hint={`${factorHints[key]} · productivity.csv`}
                onChange={(value) => setField('productivity_factors', key, value)} />
            ))}
          </div>
          </details>

          <details className="whatif-control-disclosure">
            <summary>Materials &amp; commercial</summary>
          <div className="whatif-control-group">
            <RangeControl id="whatif-material-waste" label="Material waste" value={draft.allowances.material_waste_pct}
              min="0" max="20" step="0.1" suffix="%" hint="Material quantity × catalogue or supplier rate × (1 + waste) · project parameters"
              onChange={(value) => setField('allowances', 'material_waste_pct', value)} />
            <RangeControl id="whatif-overhead" label="Overhead" value={draft.commercial.overhead_pct}
              min="0" max="30" step="0.1" suffix="%" hint="Adjusted direct cost × overhead · project parameters"
              onChange={(value) => setField('commercial', 'overhead_pct', value)} />
            <RangeControl id="whatif-target-margin" label="Target margin" value={draft.commercial.target_margin_pct}
              min="0" max="20" step="0.1" suffix="%" hint="Selling price = baseline ÷ (1 − margin), rounded up to the configured CHF increment"
              onChange={(value) => setField('commercial', 'target_margin_pct', value)} />
          </div>
          </details>

          {Object.keys(draft.labour_rates_chf_per_h).length > 0 && (
            <details className="whatif-control-disclosure">
              <summary>Labour rates</summary>
            <div className="whatif-control-group whatif-labour-group">
              <p className="whatif-group-note">Each rate starts from the role default in productivity.csv. Labour = unrounded hours × CHF/h.</p>
              {Object.entries(draft.labour_rates_chf_per_h).map(([role, value]) => (
                <RangeControl key={role} id={`whatif-rate-${role}`} label={role.replaceAll('_', ' ')} value={value}
                  min="0" max="250" step="1" suffix=" CHF/h" hint="Editable role rate · applies to matching installation rules"
                  onChange={(next) => setField('labour_rates_chf_per_h', role, next)} />
              ))}
            </div>
            </details>
          )}
        </div>

        <div className="whatif-results" aria-live="polite" aria-busy={loading || applying}>
          <div className={`whatif-offer ${preview ? 'has-preview' : ''}`}>
            <div className="whatif-offer-top">
              <span>{preview ? 'PREVIEWED SELLING PRICE' : 'CURRENT SELLING PRICE'}</span>
              {loading ? <span className="whatif-status"><LoaderCircle size={14} className="spin" /> Recalculating</span>
                : <span className="whatif-status"><Clock3 size={14} /> Revision {summary.revision}</span>}
            </div>
            <strong className="whatif-offer-price">{money(preview?.proposed.selling_price_chf ?? summary.totals.selling_price_chf)}</strong>
            {preview ? (
              <div className="whatif-offer-delta">
                {(preview.deltas.selling_price_chf.startsWith('-') ? <ArrowDownRight size={18} /> : <ArrowUpRight size={18} />)}
                <strong>{signedMoney(preview.deltas.selling_price_chf)}</strong>
                <span>· {signedPercent(preview.deltas.selling_price_pct)} vs current offer</span>
              </div>
            ) : (
              <p className="whatif-offer-hint">Adjust any control to preview the price impact.</p>
            )}
            {preview && <div className="whatif-preview-time"><Sparkles size={13} /> Previewed in {preview.elapsed_ms} ms · no revision written</div>}
          </div>

          {preview ? (
            <>
              <div className="whatif-metrics">
                <Metric label="Material" current={money(preview.current.material_chf, 2)} next={money(preview.proposed.material_chf, 2)} delta={signedMoney(preview.deltas.material_chf)} />
                <Metric label="Labour" current={money(preview.current.labour_chf, 2)} next={money(preview.proposed.labour_chf, 2)} delta={signedMoney(preview.deltas.labour_chf)} />
                <Metric label="Install hours" current={`${number(preview.current.hours, 3)} h`} next={`${number(preview.proposed.hours, 3)} h`} delta={signedHours(preview.deltas.hours)} />
                <Metric label="Cost baseline" current={money(preview.current.baseline_chf, 2)} next={money(preview.proposed.baseline_chf, 2)} delta={`${signedMoney(preview.deltas.baseline_chf)} · ${signedPercent(preview.deltas.baseline_pct)}`} />
              </div>

              <section className="whatif-scenarios" aria-label="Scenario offer changes">
                <div className="whatif-results-heading"><h3>All three bid scenarios</h3><span>current → preview</span></div>
                <div className="whatif-scenario-list">
                  {preview.deltas.scenarios.map((scenario) => (
                    <div className="whatif-scenario-row" key={scenario.scenario}>
                      <span>{scenario.scenario}</span>
                      <span>{money(scenario.current_bid_price_chf)} <ArrowRight size={12} /> <strong>{money(scenario.proposed_bid_price_chf)}</strong></span>
                      <b className={scenario.bid_price_delta_chf.startsWith('-') ? 'is-negative' : 'is-positive'}>{signedMoney(scenario.bid_price_delta_chf)}</b>
                    </div>
                  ))}
                </div>
              </section>

              <div className="whatif-affected-grid">
                <section className="whatif-affected">
                  <div className="whatif-results-heading"><h3>Most affected positions</h3><span>direct cost</span></div>
                  {preview.top_positions.length ? preview.top_positions.map((position) => (
                    <div className="whatif-impact-row" key={position.id}>
                      <div><strong>{position.reference}</strong><small>{position.description}</small></div>
                      <b className={position.direct_delta_chf.startsWith('-') ? 'is-negative' : 'is-positive'}>{signedMoney(position.direct_delta_chf)}</b>
                    </div>
                  )) : <p className="whatif-empty-impact">No position-level direct cost changed. Commercial-only changes flow through the project baseline.</p>}
                </section>
                <section className="whatif-affected">
                  <div className="whatif-results-heading"><h3>Systems</h3><span>direct cost</span></div>
                  {preview.top_systems.length ? preview.top_systems.map((system) => (
                    <div className="whatif-system-row" key={system.system}>
                      <span>{system.system}</span>
                      <b className={system.direct_delta_chf.startsWith('-') ? 'is-negative' : 'is-positive'}>{signedMoney(system.direct_delta_chf)}</b>
                    </div>
                  )) : <p className="whatif-empty-impact">No installation system shifted.</p>}
                </section>
              </div>
            </>
          ) : (
            <>
            <div className="whatif-metrics whatif-metrics-empty">
              <Metric label="Material" current="CHF 0" next="CHF 0" delta="±CHF 0 · unchanged" />
              <Metric label="Labour" current="CHF 0" next="CHF 0" delta="±CHF 0 · unchanged" />
              <Metric label="Install hours" current="0 h" next="0 h" delta="±0 h · unchanged" />
            </div>
            <div className="whatif-preview-empty">
              {loading ? <><LoaderCircle size={18} className="spin" /><span>Recalculating the estimate…</span></>
                : <><SlidersHorizontal size={18} /><span>Drag a control to see material, labour, baseline, offer and scenario changes.</span></>}
            </div></>
          )}

          {error && <div className="whatif-error" role="alert">{error}</div>}
          <div className="whatif-commit">
            <label htmlFor="whatif-reason">Reason for this assumption change</label>
            <textarea id="whatif-reason" value={reason} onChange={(event) => setReason(event.currentTarget.value)}
              placeholder="e.g. Revised access plan confirmed with site team" maxLength={2000} />
            <div className="whatif-actions">
              <button type="button" className="whatif-reset" onClick={reset} disabled={!changed && !reason}> <RotateCcw size={14} /> Reset</button>
              <button type="button" className="whatif-apply" onClick={() => void apply()}
                disabled={!preview || preview.revision !== summary.revision || reason.trim().length < 3 || loading || applying}>
                {applying ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}
                {applying ? 'Applying…' : 'Apply with reason'}
              </button>
            </div>
            <small>Apply writes all staged values as one revision. Reset discards the preview.</small>
          </div>
        </div>
      </div>
    </section>
  );
}

function Metric({ label, current, next, delta }: { label: string; current: string; next: string; delta: string }) {
  return (
    <div className="whatif-metric">
      <span>{label}</span>
      <strong className={delta.startsWith('+') ? 'delta-success' : delta.startsWith('−') || delta.startsWith('-') ? 'delta-danger' : 'delta-muted'}>{delta}</strong>
      <small>{current} → {next}</small>
    </div>
  );
}
