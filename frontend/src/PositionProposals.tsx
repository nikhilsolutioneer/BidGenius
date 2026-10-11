import { useState } from 'react';
import { Badge, Button, DetailRow, ErrorBox, Field } from './components';
import { label, money } from './api';
import type { Position } from './types';
import type { Mutate } from './Dialogs';

interface PricingProposal {
  id: string;
  product_id: string;
  description: string;
  source_type: string;
  net_unit_cost_chf: string;
  unit: string;
  install_code: string | null;
  differences: string[];
  source_span_ids: string[];
  review_state: 'pending' | 'accepted' | 'rejected';
  reason?: string;
  preview: {
    material_cost_chf: string | null;
    labour_cost_chf: string | null;
    direct_cost_chf: string | null;
    additional_known_cost_chf: string | null;
  };
}
interface RefinementProposal {
  id: string;
  changes: Record<string, unknown>;
  source_span_ids: string[];
  state: string;
  rationale: string;
}

export default function PositionProposals({ position, mutate }: { position: Position; mutate: Mutate }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const pricing = (position.attributes.pricing_proposals || []) as PricingProposal[];
  const refinements = (position.attributes.ai_refinement_proposals || []) as RefinementProposal[];
  const proposedValue = (value: unknown): string =>
    value == null ? 'Not recorded' : Array.isArray(value) ? value.join(', ')
      : typeof value === 'object' ? Object.entries(value).map(([key, item]) => `${label(key)}: ${String(item)}`).join(' · ')
      : String(value);
  if (!pricing.length && !refinements.length) return null;
  const decide = async (
    id: string,
    review_state: 'accepted' | 'rejected',
    kind: 'pricing_proposal' | 'ai_refinement_proposal',
  ) => {
    if (!reason.trim()) {
      setError('Enter a reason before accepting or rejecting a proposal.');
      return;
    }
    setBusy(id);
    setError('');
    try {
      await mutate(`/positions/${position.id}`, { reason, changes: { [kind]: { id, review_state } } });
      setReason('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="position-proposals" aria-label="Position proposals">
      <h4>Proposals for estimator approval</h4>
      <p className="text-muted">
        Pending proposals do not change the estimate. Accepting a pricing reference does not confirm technical
        equivalence.
      </p>
      {error && <ErrorBox message={error} />}
      <Field
        label="Proposal decision reason"
        hint="Record the basis for the pricing assumption or extraction correction."
      >
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
      </Field>
      {pricing.map((proposal) => (
        <article className="proposal-card" key={proposal.id}>
          <div className="inline">
            <strong>{proposal.product_id}</strong>
            <Badge tone={proposal.review_state === 'accepted' ? 'green' : 'amber'}>
              {label(proposal.review_state)}
            </Badge>
          </div>
          <p>{proposal.description}</p>
          <DetailRow name="Price provenance">{label(proposal.source_type)}</DetailRow>
          <DetailRow name="Reference net rate">
            {money(proposal.net_unit_cost_chf, 2)} / {proposal.unit}
          </DetailRow>
          <DetailRow name="Installation rule">{proposal.install_code || 'Unresolved'}</DetailRow>
          <ul>
            {proposal.differences.map((difference, index) => (
              <li key={index}>{difference}</li>
            ))}
          </ul>
          <details>
            <summary>Source lines / evidence</summary>
            <p>{proposal.source_span_ids.length} source line{proposal.source_span_ids.length === 1 ? '' : 's'} attached on PDF page {position.source_page}. Open the Source tab to inspect the highlight.</p>
          </details>
          <div className="proposal-preview">
            <strong>Preview if accepted</strong>
            <DetailRow name="Material">{money(proposal.preview?.material_cost_chf, 2)}</DetailRow>
            <DetailRow name="Labour">{money(proposal.preview?.labour_cost_chf, 2)}</DetailRow>
            <DetailRow name="Complete direct cost">{money(proposal.preview?.direct_cost_chf, 2)}</DetailRow>
            <DetailRow name="Additional known direct cost">
              {money(proposal.preview?.additional_known_cost_chf, 2)}
            </DetailRow>
          </div>
          {proposal.reason && <p>Recorded reason: {proposal.reason}</p>}
          {proposal.review_state === 'pending' && (
            <div className="inline proposal-actions">
              <Button
                variant="primary"
                disabled={busy !== null}
                onClick={() => void decide(proposal.id, 'accepted', 'pricing_proposal')}
              >
                {busy === proposal.id ? 'Saving…' : 'Approve similar catalogue rate'}
              </Button>
              <Button
                disabled={busy !== null}
                onClick={() => void decide(proposal.id, 'rejected', 'pricing_proposal')}
              >
                Reject catalogue suggestion
              </Button>
            </div>
          )}
        </article>
      ))}
      {refinements.map((proposal) => (
        <article className="proposal-card" key={proposal.id}>
          <div className="inline">
            <strong>AI extraction refinement</strong>
            <Badge>{label(proposal.state)}</Badge>
          </div>
          <p>{proposal.rationale}</p>
          {Object.entries(proposal.changes).map(([key, value]) => (
            <DetailRow key={key} name={label(key)}>
              {proposedValue(value)}
            </DetailRow>
          ))}
          <details>
            <summary>Source lines / evidence</summary>
            <p>{proposal.source_span_ids.length} source line{proposal.source_span_ids.length === 1 ? '' : 's'} attached on PDF page {position.source_page}. Open the Source tab to inspect the highlight.</p>
          </details>
          {proposal.state === 'pending' && (
            <div className="inline proposal-actions">
              <Button
                variant="primary"
                disabled={busy !== null}
                onClick={() => void decide(proposal.id, 'accepted', 'ai_refinement_proposal')}
              >
                Accept correction
              </Button>
              <Button
                disabled={busy !== null}
                onClick={() => void decide(proposal.id, 'rejected', 'ai_refinement_proposal')}
              >
                Reject correction
              </Button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
