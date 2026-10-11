import { useEffect, useState } from 'react';
import { CalendarDays, FileSpreadsheet, Upload } from 'lucide-react';
import { api, label, money, number, post, probabilityPercent } from './api';
import { Badge, Button, DetailRow, ErrorBox, Field, Spinner } from './components';
import type { Mutate } from './Dialogs';

interface HistoricalRecord {
  record_id: string;
  project_name: string;
  currency: string;
  bid_amount: string;
  outcome: string;
  project_date?: string | null;
  scope_description?: string | null;
  estimated_baseline?: string | null;
  winning_price?: string | null;
  installation_hours?: string | null;
}
interface CommercialData {
  revision: number;
  records: HistoricalRecord[];
  imports: { filename?: string; sha256?: string; imported_at?: string }[];
  context: {
    selected_record_ids: string[];
    adopt_observed_win_rate: boolean;
    adopt_reference_ratio: boolean;
    adoption_rationale: string;
    capacity: {
      period_start: string | null;
      period_end: string | null;
      available_hours: string | null;
      committed_hours: string | null;
    };
    scenario_overrides: Record<string, unknown>;
  };
  statistics: {
    selected_count: number;
    eligible_count: number;
    wins: number;
    losses: number;
    unknown: number;
    observed_win_rate: string | null;
    median_bid_to_baseline_ratio: string | null;
    ratio_sample_size: number;
    outcome_sample_size: number;
  };
  capacity: {
    remaining_hours: string | null;
    known_required_hours: string;
    shortfall_hours: string | null;
    labour_incomplete: boolean;
  };
}
interface ImportPreview {
  rows: HistoricalRecord[];
  errors: unknown[];
  duplicates: unknown[];
  valid_count: number;
  can_import: boolean;
  sha256: string;
}
const describe = (value: unknown) => typeof value === 'string' ? value : value && typeof value === 'object'
  ? Object.entries(value).filter(([key]) => !key.endsWith('_id') && key !== 'sha256')
    .map(([key, item]) => `${label(key)}: ${String(item)}`).join(' · ') : String(value);

export default function CommercialContext({ projectId, mutate }: { projectId: string; mutate: Mutate }) {
  const [data, setData] = useState<CommercialData | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [file, setFile] = useState<{ filename: string; csv_text: string } | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api<CommercialData>(`/projects/${projectId}/commercial-context`)
      .then((result) => {
        if (active) {
          setData(result);
          setSelected(result.context.selected_record_ids);
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [projectId]);
  const loadFile = async (chosen?: File) => {
    if (!chosen) return;
    setBusy(true);
    setError('');
    setPreview(null);
    try {
      const next = { filename: chosen.name, csv_text: await chosen.text() };
      setFile(next);
      setPreview(await post<ImportPreview>(`/projects/${projectId}/historical/preview`, next));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const importFile = async () => {
    if (!file || !reason.trim()) {
      setError('A reason is required to import historical records.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await mutate(`/projects/${projectId}/historical/import`, { ...file, reason }, 'POST');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel commercial-context">
      <div className="panel-header">
        <div>
          <h2>
            <FileSpreadsheet size={18} /> Historical evidence & capacity
          </h2>
          <p>Use real comparable projects and reviewed capacity inputs. Missing data stays missing.</p>
        </div>
      </div>
      <div className="panel-body">
        {error && <ErrorBox message={error} />}
        {!data && !error && <Spinner text="Loading commercial evidence…" />}
        <details className="history-import" open={Boolean(preview)}>
          <summary>Import historical bids from CSV</summary>
          <p>
            Required columns: <code>record_id, project_name, currency, bid_amount, outcome</code>. Outcomes:
            won, lost, unknown. Only CHF records are eligible for financial comparison.
          </p>
          <p>
            Optional: project_date, scope_description, estimated_baseline, winning_price, installation_hours.
            No automatic currency conversion or scope normalization is applied.
          </p>
          <Field label="Historical bid CSV">
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(e) => void loadFile(e.target.files?.[0])}
            />
          </Field>
          {preview && (
            <div className="import-preview" aria-live="polite">
              <div className="inline">
                <Badge tone={preview.can_import ? 'green' : 'amber'}>
                  {preview.valid_count} valid records
                </Badge>
                <span>
                  {preview.duplicates.length} duplicates · {preview.errors.length} errors
                </span>
              </div>
              {!!preview.errors.length && (
                <div role="alert">
                  <strong>Resolve import errors</strong>
                  <ul>
                    {preview.errors.map((entry, i) => (
                      <li key={i}>{describe(entry)}</li>
                    ))}
                  </ul>
                </div>
              )}
              {!!preview.duplicates.length && (
                <details>
                  <summary>Duplicate records</summary>
                  <ul>
                    {preview.duplicates.map((entry, i) => (
                      <li key={i}>{describe(entry)}</li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="table-scroll">
                <table className="data-table">
                  <caption className="sr-only">Historical import preview</caption>
                  <thead>
                    <tr>
                      <th>Record / project</th>
                      <th>Bid</th>
                      <th>Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 20).map((row, i) => (
                      <tr key={`${row.record_id}-${i}`}>
                        <td>
                          {row.record_id}
                          <small>{row.project_name}</small>
                        </td>
                        <td>
                          {row.currency} {number(row.bid_amount, 2)}
                        </td>
                        <td>{label(row.outcome)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.rows.length > 20 && <p>Showing the first 20 preview rows of {preview.rows.length}.</p>}
              <Field label="Historical import reason">
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Source and relevance of these records"
                />
              </Field>
              <Button
                variant="primary"
                disabled={busy || !preview.can_import || !reason.trim()}
                onClick={() => void importFile()}
              >
                <Upload size={15} />
                {busy ? 'Importing…' : 'Import reviewed records'}
              </Button>
            </div>
          )}
        </details>
        {data && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError('');
              const values = new FormData(e.currentTarget);
              try {
                await mutate(`/projects/${projectId}/commercial-context`, {
                  reason: String(values.get('reason')),
                  changes: {
                    selected_record_ids: selected,
                    adopt_observed_win_rate: values.has('adopt_win'),
                    adopt_reference_ratio: values.has('adopt_ratio'),
                    adoption_rationale: String(values.get('rationale') || ''),
                    capacity: {
                      period_start: String(values.get('period_start') || '') || null,
                      period_end: String(values.get('period_end') || '') || null,
                      available_hours: String(values.get('available') || '') || null,
                      committed_hours: String(values.get('committed') || '') || null,
                    },
                  },
                });
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="commercial-section">
              <h3>Comparable projects</h3>
              {data.records.length === 0 ? (
                <div className="note">
                  No historical bid records have been imported. Scenario probabilities remain supplied
                  heuristics.
                </div>
              ) : (
                <>
                  <p>
                    Select records whose scope is comparable. Selection alone does not change the probability
                    or reference price.
                  </p>
                  <div className="table-scroll">
                    <table className="data-table">
                      <caption className="sr-only">Select historical comparable projects</caption>
                      <thead>
                        <tr>
                          <th>Select</th>
                          <th>Project / scope</th>
                          <th>Own bid</th>
                          <th>Baseline</th>
                          <th>Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.records.map((record) => (
                          <tr key={record.record_id}>
                            <td>
                              <input
                                type="checkbox"
                                aria-label={`Use comparable ${record.project_name}`}
                                disabled={record.currency !== 'CHF'}
                                checked={selected.includes(record.record_id)}
                                onChange={(e) =>
                                  setSelected((ids) =>
                                    e.target.checked
                                      ? [...ids, record.record_id]
                                      : ids.filter((id) => id !== record.record_id),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <strong>{record.project_name}</strong>
                              <small>
                                {record.record_id} · {record.project_date || 'Date not supplied'}
                              </small>
                              <small>{record.scope_description || 'Scope description not supplied'}</small>
                            </td>
                            <td>
                              {record.currency === 'CHF'
                                ? money(record.bid_amount, 2)
                                : `${record.currency} ${number(record.bid_amount, 2)} · excluded`}
                            </td>
                            <td>
                              {record.estimated_baseline
                                ? `${record.currency} ${number(record.estimated_baseline, 2)}`
                                : 'Not supplied'}
                            </td>
                            <td>{label(record.outcome)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              <div className="commercial-statistics">
                <DetailRow name="Saved comparable sample">
                  {data.statistics.selected_count} selected · {data.statistics.eligible_count} eligible
                </DetailRow>
                <DetailRow name="Observed outcomes">
                  {data.statistics.wins} won · {data.statistics.losses} lost · {data.statistics.unknown}{' '}
                  unknown
                </DetailRow>
                <DetailRow name="Known-outcome sample">
                  {data.statistics.outcome_sample_size} records
                </DetailRow>
                <DetailRow name="Observed win rate">
                  {data.statistics.observed_win_rate == null
                    ? 'No usable outcomes'
                    : `${probabilityPercent(data.statistics.observed_win_rate)}%`}
                </DetailRow>
                <DetailRow name="Paired-price sample">{data.statistics.ratio_sample_size} records</DetailRow>
                <DetailRow name="Median bid / baseline">
                  {data.statistics.median_bid_to_baseline_ratio == null
                    ? 'No usable paired prices'
                    : number(data.statistics.median_bid_to_baseline_ratio, 4)}
                </DetailRow>
              </div>
              <p className="text-muted">
                Statistics reflect the saved selection. Unknown outcomes are excluded from the win rate. A
                small or dissimilar sample is not a calibrated prediction.
              </p>
              <label className="commercial-checkbox">
                <input
                  type="checkbox"
                  name="adopt_win"
                  defaultChecked={data.context.adopt_observed_win_rate}
                  disabled={!data.records.length}
                />
                <span>Adopt observed win rate as the scenario reference probability</span>
              </label>
              <label className="commercial-checkbox">
                <input
                  type="checkbox"
                  name="adopt_ratio"
                  defaultChecked={data.context.adopt_reference_ratio}
                  disabled={!data.records.length}
                />
                <span>Adopt the median comparable bid-to-baseline ratio as the reference-price basis</span>
              </label>
              <Field
                label="Historical adoption rationale"
                hint="Required when adopting either historical statistic. Explain scope comparability and limitations."
              >
                <textarea name="rationale" defaultValue={data.context.adoption_rationale} rows={2} />
              </Field>
            </div>
            <div className="commercial-section">
              <h3>
                <CalendarDays size={17} /> Installation capacity
              </h3>
              <p>
                Record capacity for the planned installation period. Capacity does not automatically change
                prices or probabilities.
              </p>
              <div className="form-grid">
                <Field label="Capacity period start">
                  <input
                    name="period_start"
                    type="date"
                    defaultValue={data.context.capacity.period_start || ''}
                  />
                </Field>
                <Field label="Capacity period end">
                  <input
                    name="period_end"
                    type="date"
                    defaultValue={data.context.capacity.period_end || ''}
                  />
                </Field>
                <Field
                  label="Available installation hours"
                  hint="Both period dates are required when entering hours."
                >
                  <input
                    name="available"
                    type="number"
                    min="0"
                    step="0.01"
                    defaultValue={data.context.capacity.available_hours || ''}
                  />
                </Field>
                <Field label="Already committed hours" hint="Enter 0 explicitly if there are no commitments.">
                  <input
                    name="committed"
                    type="number"
                    min="0"
                    step="0.01"
                    defaultValue={data.context.capacity.committed_hours || ''}
                  />
                </Field>
              </div>
              <div className="commercial-statistics">
                <DetailRow name="Saved remaining capacity">
                  {data.capacity.remaining_hours == null
                    ? 'Not supplied'
                    : `${number(data.capacity.remaining_hours)} h`}
                </DetailRow>
                <DetailRow name="Known project labour demand">
                  {number(data.capacity.known_required_hours)} h
                </DetailRow>
                <DetailRow name="Known capacity shortfall">
                  {data.capacity.shortfall_hours == null
                    ? 'Not assessed'
                    : `${number(data.capacity.shortfall_hours)} h`}
                </DetailRow>
              </div>
              {data.capacity.labour_incomplete && (
                <div className="note">
                  Labour coverage is incomplete. Known demand understates the full requirement; a displayed
                  zero shortfall does not establish sufficient capacity.
                </div>
              )}
            </div>
            <Field label="Commercial context change reason">
              <input name="reason" required placeholder="Why these comparables or capacity inputs apply" />
            </Field>
            <div className="form-bottom">
              <span className="text-muted">
                Saving creates a revision with the evidence and inputs used by exports.
              </span>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? 'Saving…' : 'Save commercial context'}
              </Button>
            </div>
          </form>
        )}
        {!!data?.imports.length && (
          <details className="commercial-section">
            <summary>Imported source files</summary>
            {data.imports.map((record, i) => (
              <div key={i}>
                <strong>{record.filename || 'Historical CSV'}</strong>
                <small className="source-hash">{record.sha256}</small>
              </div>
            ))}
          </details>
        )}
      </div>
    </section>
  );
}
