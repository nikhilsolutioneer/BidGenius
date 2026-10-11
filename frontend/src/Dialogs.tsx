import { useState } from 'react';
import type { FormEvent } from 'react';
import { AlertTriangle, ArrowRight, Check, Save } from 'lucide-react';
import { ApiError, label, money } from './api';
import { Button, ErrorBox, Field, Modal, Badge } from './components';
import type { Position, Project, References, SourceSpan, Adjustment, RecordData } from './types';
export type Mutate = (path: string, body: RecordData, method?: 'POST' | 'PATCH') => Promise<unknown>;
const systems = ['LA01', 'LA02', 'LA03', 'LA04', 'LA05', 'ROOF', 'Unassigned'];
const emptyNull = (v: FormDataEntryValue | null) => (typeof v === 'string' && v.trim() ? v.trim() : null);
export function PositionDialog({
  position,
  references,
  onClose,
  mutate,
}: {
  position: Position;
  references: References | null;
  onClose: () => void;
  mutate: Mutate;
}) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const f = new FormData(e.currentTarget);
    const overrides: RecordData = {};
    for (const k of ['net_unit_cost_chf', 'hourly_rate_chf', 'material_waste_pct']) {
      const value = emptyNull(f.get(k));
      if (String(value ?? '') !== String(position.overrides[k] ?? '')) overrides[k] = value;
    }
    const factors: RecordData = {};
    for (const k of Object.keys(references?.parameters.productivity_factors || {})) {
      const value = emptyNull(f.get(`factor.${k}`));
      if (value !== null) factors[k] = value;
    }
    if (JSON.stringify(factors) !== JSON.stringify(position.overrides.factor_overrides || {}))
      overrides.factor_overrides = factors;
    const inclusions = String(f.get('scope_inclusions') || '')
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean);
    const existingInclusions = (position.overrides.scope_inclusions ||
      position.attributes.inclusions ||
      []) as string[];
    if (JSON.stringify(inclusions) !== JSON.stringify(existingInclusions))
      overrides.scope_inclusions = inclusions;
    const values: RecordData = {
      description: f.get('description'),
      quantity: emptyNull(f.get('quantity')),
      unit: emptyNull(f.get('unit')),
      system: f.get('system'),
      category: f.get('category'),
      product_id: emptyNull(f.get('product_id')),
      install_code: emptyNull(f.get('install_code')),
      review_state: f.get('review_state'),
      technical_equivalence: f.get('technical_equivalence'),
      included_in: emptyNull(f.get('included_in')),
      status: f.get('scope_status'),
    };
    const changes: RecordData = {};
    for (const [k, v] of Object.entries(values)) {
      if (v !== (position as unknown as RecordData)[k]) changes[k] = v;
    }
    if (Object.keys(overrides).length) changes.overrides = overrides;
    if (!Object.keys(changes).length) {
      setError('Change at least one value, or use Accept review to record a review decision.');
      setSaving(false);
      return;
    }
    try {
      await mutate(`/positions/${position.id}`, { reason: f.get('reason'), changes });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Review position"
      description="Changes create an auditable revision and recalculate the estimate."
      wide
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <ErrorBox message={error} />}
          <div className="source-quote" tabIndex={0} translate="no" lang="de">{position.original_description || position.description}</div>
          <div className="form-grid">
            <Field label="Description">
              <input name="description" defaultValue={position.description} required />
            </Field>
            <Field label="System">
              <select name="system" defaultValue={position.system}>
                {systems.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Quantity" hint="Leave empty if the quantity is unknown.">
              <input
                name="quantity"
                type="number"
                min="0"
                step="any"
                defaultValue={position.quantity || ''}
              />
            </Field>
            <Field label="Unit">
              <select name="unit" defaultValue={position.unit || ''}>
                <option value="">Unknown</option>
                {['pc', 'm', 'm2', 'h', 'LS', 'system'].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Category">
              <input name="category" defaultValue={position.category} required />
            </Field>
            <Field label="Pricing reference">
              <select name="product_id" defaultValue={position.product_id || ''}>
                <option value="">No product selected</option>
                {references?.catalog.map((c) => (
                  <option key={c.product_id} value={c.product_id}>
                    {c.product_id} ·{' '}
                    {c.description || c.description_de || c.product_name || c.name || c.category}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Installation rule">
              <select name="install_code" defaultValue={position.install_code || ''}>
                <option value="">No rule selected</option>
                {references?.productivity.map((p, i) => (
                  <option key={p.install_code || i} value={p.install_code}>
                    {p.install_code} · {p.description || p.labour_role || p.category}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Review state">
              <select name="review_state" defaultValue={position.review_state}>
                <option value="pending">Pending</option>
                <option value="accepted">Accepted</option>
                <option value="rejected">Rejected</option>
              </select>
            </Field>
            <Field label="Technical equivalence">
              <select name="technical_equivalence" defaultValue={position.technical_equivalence}>
                <option value="unverified">Unverified</option>
                <option value="reviewer_confirmed">Confirmed by reviewer</option>
                <option value="incompatible">Incompatible</option>
              </select>
            </Field>
          </div>
          <h4>Optional pricing overrides</h4>
          <div className="form-grid three">
            <Field label="Net unit cost · CHF">
              <input
                name="net_unit_cost_chf"
                type="number"
                min="0"
                step="any"
                defaultValue={String(position.overrides.net_unit_cost_chf ?? '')}
                placeholder={position.cost?.net_unit_cost_chf || 'From reference'}
              />
            </Field>
            <Field label="Labour rate · CHF/h">
              <input
                name="hourly_rate_chf"
                type="number"
                min="0"
                step="any"
                defaultValue={String(position.overrides.hourly_rate_chf ?? '')}
                placeholder={position.cost?.hourly_rate_chf || 'From rule'}
              />
            </Field>
            <Field label="Material waste · %">
              <input
                name="material_waste_pct"
                type="number"
                min="0"
                step="any"
                defaultValue={String(position.overrides.material_waste_pct ?? '')}
                placeholder="Project assumption"
              />
            </Field>
          </div>
          <details className="advanced-edit">
            <summary>Installation factors & scope ownership</summary>
            <div className="form-grid">
              {Object.entries(references?.parameters.productivity_factors || {}).map(([k, v]) => (
                <Field key={k} label={label(k)} hint="Blank inherits the project assumption.">
                  <input
                    name={`factor.${k}`}
                    type="number"
                    min="0.01"
                    step="any"
                    defaultValue={String(
                      (position.overrides.factor_overrides as RecordData | undefined)?.[k] ?? '',
                    )}
                    placeholder={String(v)}
                  />
                </Field>
              ))}
            </div>
            <Field
              label="Scope treatment"
              hint="Exclusions require a reason and remain traceable in the estimate."
            >
              <select name="scope_status" defaultValue={position.status}>
                <option value={position.status}>Current outcome: {label(position.status)}</option>
                {['out_of_scope', 'non_priceable', 'review_required']
                  .filter((v) => v !== position.status)
                  .map((v) => (
                    <option key={v} value={v}>
                      {label(v)}
                    </option>
                  ))}
              </select>
            </Field>
            <Field
              label="Cost scope owner"
              hint="Position ID or project:commissioning, project:documentation, etc. Blank means owned by this position."
            >
              <input name="included_in" defaultValue={position.included_in || ''} />
            </Field>
            <Field
              label="Package inclusions"
              hint="Comma-separated scopes: installation, transport, small_material, supplier_contingency, commissioning, documentation."
            >
              <input
                name="scope_inclusions"
                defaultValue={(
                  (position.overrides.scope_inclusions || position.attributes.inclusions || []) as string[]
                ).join(', ')}
              />
            </Field>
            <div className="note">
              Package inclusions prevent costs from being charged again. The calculation engine validates
              ownership and scope overlap.
            </div>
          </details>
          <Field label="Reason for this change">
            <textarea
              name="reason"
              minLength={3}
              required
              rows={2}
              placeholder="Explain the evidence or commercial assumption behind this decision."
            />
          </Field>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            <Save size={16} />
            {saving ? 'Recalculating…' : 'Save and recalculate'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function ManualDialog({
  spans,
  project,
  onClose,
  mutate,
  onSelect,
}: {
  spans: SourceSpan[];
  project: Project;
  onClose: () => void;
  mutate: Mutate;
  onSelect: (id: string) => void;
}) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [duplicates, setDuplicates] = useState<Position[]>([]);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const f = new FormData(e.currentTarget);
    try {
      const res = (await mutate(`/projects/${project.id}/positions`, {
        reason: f.get('reason'),
        source_span_ids: spans.map((s) => s.id),
        description: f.get('description'),
        system: f.get('system'),
        category: f.get('category'),
        quantity: emptyNull(f.get('quantity')),
        unit: emptyNull(f.get('unit')),
        acknowledge_duplicate: f.get('acknowledge') === 'on',
      })) as { position: Position };
      onSelect(res.position.id);
      onClose();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError) {
        const d = e.details as { duplicates?: Position[] };
        if (d.duplicates) setDuplicates(d.duplicates);
      }
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Add a position from evidence"
      description="Recover missing scope while preserving the original source."
      wide
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <ErrorBox message={error} />}
          <div className="section-label">ORIGINAL GERMAN EVIDENCE · PAGE {spans[0]?.page}</div>
          <div className="source-quote" tabIndex={0}>{spans.map((s) => s.text).join('\n')}</div>
          <Field label="Description">
            <textarea
              name="description"
              defaultValue={spans.map((s) => s.text).join(' ')}
              required
              minLength={2}
              rows={3}
            />
          </Field>
          <div className="form-grid">
            <Field label="System">
              <select name="system" defaultValue="Unassigned">
                {systems.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Category">
              <input name="category" defaultValue="unclassified" required />
            </Field>
            <Field label="Quantity" hint="Unknown quantities remain unpriced.">
              <input type="number" min="0" step="any" name="quantity" />
            </Field>
            <Field label="Unit">
              <select name="unit">
                <option value="">Unknown</option>
                {['pc', 'm', 'm2', 'h', 'LS', 'system'].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="note">
            <AlertTriangle size={16} />
            Values not supported by the selected evidence will be recorded as manual assumptions.
          </div>
          {duplicates.length > 0 && (
            <div className="duplicate-box">
              <h4>Possible existing positions</h4>
              {duplicates.map((p) => (
                <button
                  type="button"
                  key={p.id}
                  className="text-btn"
                  onClick={() => {
                    onSelect(p.id);
                    onClose();
                  }}
                >
                  {p.description.slice(0, 90)} <ArrowRight size={14} />
                </button>
              ))}
              <label className="check-label">
                <input type="checkbox" name="acknowledge" required /> This is an intentional split or separate
                scope. My reason explains why.
              </label>
            </div>
          )}
          <Field label="Reason for adding this position">
            <textarea name="reason" minLength={3} required rows={2} />
          </Field>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            <Check size={16} />
            {saving ? 'Adding position…' : 'Add and calculate'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function AssumptionsDialog({
  project,
  onClose,
  mutate,
}: {
  project: Project;
  onClose: () => void;
  mutate: Mutate;
}) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const groups = ['productivity_factors', 'allowances', 'project_costs', 'commercial', 'duct_pricing'];
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const f = new FormData(e.currentTarget);
    const changes: RecordData = {};
    for (const group of groups) {
      const obj: RecordData = {};
      for (const key of Object.keys(project.parameters[group] || {})) {
        const v = f.get(`${group}.${key}`);
        if (v !== null && v !== '') obj[key] = String(v);
      }
      changes[group] = obj;
    }
    try {
      await mutate(`/projects/${project.id}/assumptions`, { reason: f.get('reason'), changes });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Project assumptions"
      description="These inputs determine the cost build-up. Every edit creates a revision."
      wide
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <ErrorBox message={error} />}
          <div className="note">
            Allowance bases are editable prototype assumptions. School and sports-hall height factors apply to
            their respective scope.
          </div>
          {groups.map((g) => (
            <section key={g} className="assumption-group">
              <h4>{label(g)}</h4>
              <div className="form-grid">
                {Object.entries(project.parameters[g] || {})
                  .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                  .map(([k, v]) => (
                    <Field key={k} label={label(k)}>
                      {k === 'rect_fitting_material_mode' ? (
                        <select name={`${g}.${k}`} defaultValue={String(v)}>
                          <option value="quote_required">Quote required</option>
                          <option value="equivalent_area">Equivalent area</option>
                        </select>
                      ) : k === 'rect_duct_area_rate_enabled' || k === 'lt_area_rate_enabled' ? (
                        <select name={`${g}.${k}`} defaultValue={String(v)}>
                          <option value="false">Off</option>
                          <option value="true">On</option>
                        </select>
                      ) : (
                        <input
                          name={`${g}.${k}`}
                          type="number"
                          min="0"
                          step="any"
                          required
                          defaultValue={String(v)}
                        />
                      )}
                    </Field>
                  ))}
              </div>
            </section>
          ))}
          <Field label="Reason for changing assumptions">
            <textarea name="reason" minLength={3} required rows={2} />
          </Field>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Recalculating…' : 'Apply and recalculate'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function AdjustmentDialog({
  project,
  adjustment,
  onClose,
  mutate,
}: {
  project: Project;
  adjustment?: Adjustment;
  onClose: () => void;
  mutate: Mutate;
}) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const f = new FormData(e.currentTarget);
    const isEdit = Boolean(adjustment?.id);
    const values = {
      kind: f.get('kind'),
      title: f.get('title'),
      amount_chf: f.get('amount'),
      scope: f.get('scope'),
      basis: f.get('basis'),
      overlap_resolution: emptyNull(f.get('overlap_resolution')),
    };
    try {
      if (isEdit && adjustment)
        await mutate(`/adjustments/${adjustment.id}`, { reason: f.get('reason'), changes: values });
      else
        await mutate(`/projects/${project.id}/adjustments`, { reason: f.get('reason'), ...values }, 'POST');
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  const isEdit = Boolean(adjustment?.id);
  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? 'Edit commercial adjustment' : 'New commercial adjustment'}
      description="Only approved adjustments affect the estimate. Unsupported savings are never generated."
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          {error && <ErrorBox message={error} />}
          <div className="form-grid">
            <Field label="Type">
              <select name="kind" defaultValue={adjustment?.kind || 'risk'}>
                <option value="risk">Risk allowance · add cost</option>
                <option value="opportunity">Opportunity · reduce cost</option>
              </select>
            </Field>
            <Field label="Amount · CHF">
              <input
                type="number"
                name="amount"
                min="0.01"
                step="0.01"
                defaultValue={adjustment?.amount_chf}
                required
              />
            </Field>
          </div>
          <Field label="Title">
            <input
              name="title"
              defaultValue={adjustment?.title}
              minLength={3}
              required
              placeholder="For example, restricted access equipment"
            />
          </Field>
          <Field label="Affected scope">
            <input name="scope" defaultValue={adjustment?.scope || 'project_level'} required />
          </Field>
          <Field label="Basis and evidence">
            <textarea
              name="basis"
              rows={3}
              minLength={3}
              defaultValue={adjustment?.basis}
              required
              placeholder="Describe the supporting evidence and how this amount was determined."
            />
          </Field>
          <Field
            label="Scope overlap resolution"
            hint="If flagged, explain precisely how this scope differs from existing allowances. Leave empty when not applicable."
          >
            <textarea
              name="overlap_resolution"
              rows={2}
              defaultValue={adjustment?.overlap_resolution || ''}
            />
          </Field>
          <Field label="Reason">
            <textarea name="reason" minLength={3} required rows={2} />
          </Field>
          <div className="note">
            Existing supplier contingency and project allowances cannot be charged again.{' '}
            {adjustment?.review_state === 'accepted'
              ? 'Editing this adjustment returns it to pending review.'
              : ''}
          </div>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save as pending'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function ReasonDialog({
  title,
  description,
  onClose,
  onSubmit,
  delta,
}: {
  title: string;
  description: string;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<unknown>;
  delta?: string;
}) {
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  return (
    <Modal open onClose={onClose} title={title} description={description}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          setError('');
          try {
            await onSubmit(String(new FormData(e.currentTarget).get('reason')));
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <div className="modal-body">
          {error && <ErrorBox message={error} />}{' '}
          {delta && <Badge tone="blue">Amount: {money(delta, 2)}</Badge>}
          <Field label="Reason for this decision">
            <textarea name="reason" required minLength={3} rows={3} autoFocus />
          </Field>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving…' : 'Confirm decision'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
