import { ArrowRight, ChartNoAxesCombined } from 'lucide-react';
import { useState } from 'react';
import { money } from './api';
import { Button } from './components';
import type { Summary } from './types';
import { Waterfall } from './charts/Waterfall';
import { EstimatorCharts } from './charts/EstimatorCharts';
import { Donut } from './charts/Donut';

export default function Analytics({ summary, onEstimate, onScenarios }: { summary: Summary; onEstimate: () => void; onScenarios: () => void }) {
  const [view, setView] = useState('mix');
  const largest = [...summary.by_system].sort((a, b) => Number(b.amount_chf) - Number(a.amount_chf))[0];
  return <div className="page-content analytics-page">
    <div className="page-heading">
      <div><div className="eyebrow">ESTIMATOR INTELLIGENCE</div><h1>See the cost. Find the gaps.</h1><p>Understand what drives the offer and where to focus your next decision.</p></div>
      <Button onClick={onScenarios}>Test assumptions <ArrowRight size={16} /></Button>
    </div>
    <div className="analytics-metrics">
      <section><span>Included-scope offer</span><strong>{money(summary.totals.selling_price_chf)}</strong><small>Saved indicative price · before VAT</small></section>
      <section><span>Unpriced benchmark exposure</span><strong>{summary.completeness ? `${money(summary.completeness.allowance_low_chf)} – ${money(summary.completeness.allowance_high_chf)}` : 'Not available'}</strong><small>Advisory range · excluded from the offer</small></section>
      <section><span>Still without a benchmark basis</span><strong>{summary.completeness?.positions_no_basis ?? '—'} <small>positions</small></strong><small>Unknown exposure remains outside the range</small></section>
    </div>
    <div className="analytics-insight"><ChartNoAxesCombined size={22} aria-hidden="true" /><p>{largest ? <><strong>{largest.label || largest.key}</strong> carries the largest allocated cost at <strong>{money(largest.amount_chf)}</strong>. Start here for cost optimisation; use unpriced allowances to prioritise quotations.</> : 'Review cost drivers and unresolved scope before committing to an offer.'}</p><Button onClick={onEstimate}>Review positions <ArrowRight size={14} /></Button></div>
    <div className="analytics-grid">
      <section className="panel analytics-card">
        <div className="panel-header analytics-visual-heading"><div><h2>{view === 'mix' ? 'Material & labour cost mix' : view === 'coverage' ? 'How much scope is priced?' : 'How the estimate adds up'}</h2><p>Read the balance of cost and the extent of unresolved scope.</p></div>
          <div className="analytics-view-switch" role="group" aria-label="Cost and coverage chart">{[['mix', 'Cost mix'], ['coverage', 'Pricing coverage'], ['build', 'Cost build-up']].map(([key, title]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)}>{title}</button>)}</div>
        </div>
        {view === 'mix' ? <Donut title="Material and labour cost mix" unit="Known cost" note="Known material and labour only. Other allowances, overhead, margin and unpriced scope are excluded." items={[
          { label: 'Material', value: Number(summary.totals.material_cost_chf || 0), formatted: money(summary.totals.material_cost_chf) },
          { label: 'Labour', value: Number(summary.totals.labour_cost_chf || 0), formatted: money(summary.totals.labour_cost_chf) },
        ]} /> : view === 'coverage' ? <Donut title="Pricing coverage by position count" unit="Positions" note="Position counts, not value shares. Unpriced positions are unknown costs, not zero costs." items={[
          { label: 'Priced', value: summary.coverage.positions_priced, formatted: `${summary.coverage.positions_priced} positions` },
          { label: 'Covered elsewhere', value: summary.coverage.positions_included_elsewhere || 0, formatted: `${summary.coverage.positions_included_elsewhere || 0} positions` },
          { label: 'Unpriced', value: summary.coverage.positions_unpriced, formatted: `${summary.coverage.positions_unpriced} positions` },
        ]} /> : <Waterfall steps={summary.build_up} baseline={summary.totals.cost_baseline_chf} offer={summary.totals.selling_price_chf} />}
      </section>
      <section className="panel analytics-card"><EstimatorCharts summary={summary} /></section>
    </div>
  </div>;
}
