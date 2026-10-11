import type {
  Document,
  Run,
  Issue,
  CommercialAdjustment as Adjustment,
  ReviewDecision as History,
} from './generated/contracts';
export type {
  Document,
  Run,
  SourceSpan,
  Issue,
  MatchCandidate as Candidate,
  CostLine as Cost,
  Position,
  CommercialAdjustment as Adjustment,
  ReviewDecision as History,
} from './generated/contracts';
export type RecordData = Record<string, unknown>;
export interface Project {
  id: string;
  name: string;
  revision: number;
  document: Document;
  parameters: Record<string, Record<string, unknown>>;
  latest_run: Run | null;
  created_at: string;
  updated_at: string;
  estimator?: string;
  bid_status?: 'draft' | 'in_review' | 'approved' | 'submitted';
}
export interface Bucket {
  key: string;
  label: string;
  material_cost_chf: string;
  labour_cost_chf: string;
  amount_chf: string;
  positions: number;
  unpriced: number;
}
export interface Scenario {
  scenario: string;
  bid_price_chf: string;
  margin_pct: string;
  achieved_margin_pct: string;
  estimated_win_probability: string;
  expected_contribution_chf: string;
  price_vs_reference_pct: string | null;
}
export interface Scenarios {
  scenarios: Scenario[];
  low_chf: string;
  high_chf: string;
  probability_curve?: { price_chf: string; estimated_win_probability: string; achieved_margin_pct: string; expected_contribution_chf: string }[];
  assumptions: unknown;
  label: string;
  reference_context?: {
    defaults_available: boolean;
    source?: string;
    reference_price_chf?: string;
    reference_margin_pct?: string;
    default_reference_price_chf?: string;
    default_reference_margin_pct?: string;
    reference_price_differs_from_default?: boolean;
    reference_margin_differs_from_default?: boolean;
  };
  commercial_evidence?: { context?: { adopt_observed_win_rate?: boolean; adopt_reference_ratio?: boolean } };
}
export interface Summary {
  project_id: string;
  revision: number;
  name: string;
  document: Document;
  parameters: Record<string, Record<string, unknown>>;
  totals: Record<string, string>;
  build_up: { key: string; label: string; amount_chf: string; formula: string; basis: string }[];
  by_system: Bucket[];
  by_category: Bucket[];
  issue_groups?: { group_key: string; kind: string; detail: string; count: number; pages: number[]; source_span_ids: string[]; issue_ids: string[] }[];
  review_cause_stakes?: { cause: string; count: number; stake_chf: string; formula?: string; source?: string }[];
  likely_total_low?: string;
  likely_total_median?: string;
  likely_total_high?: string;
  likely_total_label?: string;
  coverage: {
    pages_processed: number;
    total_pages: number;
    positions_extracted: number;
    positions_manual: number;
    positions_priced: number;
    positions_unpriced: number;
    positions_included_elsewhere?: number | null;
    provisional_priced_positions?: number | null;
    provisional_direct_cost_chf: string;
    pending_reviews: number;
    unassigned_blocks: number;
    failed_pages: number;
    partial_pages?: number;
    unresolved_by_cause?: Record<string, number>;
    partial_cost_positions?: number;
  };
  unresolved_sources?: { id: string; page: number; text: string }[];
  page_outcomes?: {
    page: number;
    status: string;
    extraction_status: string;
    system: string;
    printed_label: string | null;
    warnings: string[];
  }[];
  issues: Issue[];
  requirements: {
    id: string;
    title: string;
    description: string;
    source_page: number;
    source_span_ids: string[];
    category: string;
    review_state: string;
  }[];
  adjustments: Adjustment[];
  assumptions: unknown[];
  scope_allocations: unknown[];
  scenarios: Scenarios;
  scenario_reference?: Scenarios['reference_context'];
  completeness?: {
    positions_total: number;
    positions_priced: number;
    positions_unpriced: number;
    positions_included_elsewhere: number;
    positions_partial: number;
    positions_with_allowance: number;
    positions_no_basis: number;
    allowance_low_chf: string;
    allowance_median_chf: string;
    allowance_high_chf: string;
    priced_direct_cost_chf: string;
    estimated_total_direct_value_chf: string;
    pct_value_priced: string;
    pct_positions_priced?: string | null;
    benchmark_groups: {
      install_code: string;
      unit: string;
      sample_size: number;
      median_unit_rate_chf: string;
      p25_unit_rate_chf: string;
      p75_unit_rate_chf: string;
      references: string[];
    }[];
    itemized_allowances: {
      position_id: string;
      reference: string;
      description: string;
      install_code: string;
      unit: string;
      quantity: string | null;
      basis_status: string;
      no_basis_reason?: string;
      median_unit_rate_chf: string | null;
      allowance_median_chf: string | null;
      allowance_low_chf: string | null;
      allowance_high_chf: string | null;
      known_partial_chf: string;
      benchmark_references: string[];
      benchmark_sample_size: number;
    }[];
  };
  latest_run: Run | null;
  review_complete: boolean;
  history: History[];
}
export interface WhatIfTotals {
  material_chf: string;
  labour_chf: string;
  hours: string;
  baseline_chf: string;
  selling_price_chf: string;
  scenarios: Scenario[];
}
export interface WhatIfPreview {
  revision: number;
  elapsed_ms: number;
  current: WhatIfTotals;
  proposed: WhatIfTotals;
  deltas: {
    material_chf: string;
    labour_chf: string;
    hours: string;
    baseline_chf: string;
    selling_price_chf: string;
    baseline_pct: string | null;
    selling_price_pct: string | null;
    scenarios: { scenario: string; current_bid_price_chf: string; proposed_bid_price_chf: string; bid_price_delta_chf: string }[];
  };
  top_positions: { id: string; reference: string; description: string; system: string; material_delta_chf: string; labour_delta_chf: string; direct_delta_chf: string; hours_delta: string }[];
  top_systems: { system: string; material_delta_chf: string; labour_delta_chf: string; direct_delta_chf: string }[];
}
export interface References {
  catalog: Record<string, string>[];
  productivity: Record<string, string>[];
  parameters: Project['parameters'];
}
export interface Health {
  status: string;
  version: string;
  ai_configured: boolean;
  processing_modes?: string[];
  model: string;
}
