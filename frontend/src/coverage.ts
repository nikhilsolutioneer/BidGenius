import type { Position } from './types';

export const missingCauseLabels: Record<string, string> = {
  missing_quantity: 'Missing quantity',
  missing_material_reference: 'Missing material reference',
  missing_installation_rule: 'Missing installation rule',
  technical_conflict: 'Technical conflict',
  quotation_required: 'Quotation required',
  proxy_pending: 'Rate from similar catalogue item awaiting approval',
};

export function missingCauses(p: Position): string[] {
  if (['out_of_scope', 'non_priceable'].includes(p.status) || p.included_in) return [];
  const causes: string[] = Array.isArray(p.attributes.unresolved_causes)
    ? [...(p.attributes.unresolved_causes as string[])]
    : [];
  if (Array.isArray(p.attributes.unresolved_causes)) {
    if (
      Array.isArray(p.attributes.pricing_proposals) &&
      p.attributes.pricing_proposals.some(
        (proposal: { review_state?: string }) => proposal.review_state === 'pending',
      )
    )
      causes.push('proxy_pending');
    return [...new Set(causes)];
  }
  if (p.quantity == null) causes.push('missing_quantity');
  if (p.cost?.material_cost_chf == null && p.pricing_basis !== 'labour_only')
    causes.push('missing_material_reference');
  if (!p.install_code || p.install_code === 'UNKNOWN') causes.push('missing_installation_rule');
  if (p.match_evidence_band === 'conflicting' || p.technical_equivalence === 'incompatible')
    causes.push('technical_conflict');
  if (p.status === 'supplier_quote_required' || p.pricing_basis === 'supplier_reference')
    causes.push('quotation_required');
  if (
    Array.isArray(p.attributes.pricing_proposals) &&
    p.attributes.pricing_proposals.some(
      (proposal: { review_state?: string; status?: string }) =>
        (proposal.review_state || proposal.status) === 'pending',
    )
  )
    causes.push('proxy_pending');
  return causes;
}
