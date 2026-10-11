import { useState } from 'react';
import { label, money } from '../api';
import type { Summary } from '../types';
import { ChartTableToggle } from './ChartTableToggle';

export function EstimatorCharts({ summary }: { summary: Summary }) {
  const [view, setView] = useState('cost');
  const currency = view !== 'unpriced';
  const titles: Record<string, string> = {
    cost: 'Cost concentration by system',
    allowance: 'Largest unpriced benchmark allowances',
    unpriced: 'Unpriced positions by system',
  };
  const notes: Record<string, string> = {
    cost: 'Focus cost optimisation on the largest allocated system costs. Unpriced scope is not included.',
    allowance: 'Prioritise quotations for the ten largest median benchmark gaps. Advisory only, not included in the bid. Positions without a basis are excluded, not valued at zero.',
    unpriced: 'Focus estimating effort on systems with the most unresolved positions. Counts show workload, not financial exposure.',
  };
  const items = (view === 'allowance'
    ? (summary.completeness?.itemized_allowances || [])
      .filter(item => item.allowance_median_chf !== null)
      .map(item => ({ id: item.position_id, name: item.reference, detail: item.description, value: Number(item.allowance_median_chf), raw: item.allowance_median_chf! }))
    : summary.by_system.map(item => ({ id: item.key, name: item.label || label(item.key), detail: `${item.positions} positions · ${item.unpriced} unpriced`, value: view === 'cost' ? Number(item.amount_chf) : item.unpriced, raw: view === 'cost' ? item.amount_chf : String(item.unpriced) })))
    .sort((a, b) => b.value - a.value);
  const visible = view === 'allowance' ? items.slice(0, 10) : items;
  const max = Math.max(1, ...visible.map(item => item.value));
  return <>
    <div className="panel-header estimator-chart-heading">
      <div><h2>{titles[view]}</h2><p>{notes[view]}</p></div>
      <div className="analytics-view-switch" role="group" aria-label="Estimator chart">
        {([['cost', 'Cost by system'], ['allowance', 'Unpriced exposure'], ['unpriced', 'Review workload']] as const).map(([id, title]) => <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>{title}</button>)}
      </div>
    </div>
    <ChartTableToggle key={view} label={`${titles[view]}. ${notes[view]}`} headers={['System / reference', 'Details', currency ? 'CHF' : 'Unpriced positions']} rows={visible.map(item => [item.name, item.detail, currency ? money(item.raw) : item.value])}>
      <div className="estimator-bars" role="img" aria-label={titles[view]}>
        {visible.length === 0 && <p>No data available for this chart.</p>}
        <svg className="estimator-svg" viewBox={`0 0 620 ${Math.max(110, visible.length * 42 + 38)}`} role="img" aria-label={titles[view]}>
          {[0, .5, 1].map(tick => <g key={tick}><line x1={190 + tick * 300} x2={190 + tick * 300} y1="8" y2={visible.length * 42 + 8} className="chart-axis" /><text x={190 + tick * 300} y={visible.length * 42 + 28} textAnchor="middle">{currency ? money(String(max * tick)) : Math.round(max * tick)}</text></g>)}
          {visible.map((item, index) => <g className="estimator-bar-row" key={item.id}>
            <title>{item.name}: {currency ? money(item.raw) : `${item.value} positions`}. {item.detail}</title>
            <text x="0" y={index * 42 + 27}>{item.name.length > 25 ? `${item.name.slice(0, 23)}…` : item.name}</text>
            <rect x="190" y={index * 42 + 12} width={Math.max(0, item.value / max * 300)} height="22" rx="4" fill={index === 0 ? 'var(--viz-highlight)' : 'var(--viz-accent)'} />
            <text x="612" y={index * 42 + 27} textAnchor="end">{currency ? money(item.raw) : item.value}</text>
          </g>)}
        </svg>
      </div>
    </ChartTableToggle>
  </>;
}
