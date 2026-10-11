import { compareDecimal, money } from '../api';
import { ChartTableToggle } from './ChartTableToggle';

type Step = { key: string; label: string; amount_chf: string; formula: string; basis?: string };

export function Waterfall({ steps, baseline, offer }: { steps: Step[]; baseline: string; offer: string }) {
  const visible = steps.filter(step => compareDecimal(step.amount_chf, '0') !== 0);
  const max = Math.max(...visible.map(step => Math.abs(Number(step.amount_chf))), 1);
  const rows = [...visible.map(step => [step.label, money(step.amount_chf), step.formula]), ['Cost baseline', money(baseline), 'Saved calculated total'], ['Offer price', money(offer), 'Saved calculated total']];
  return <ChartTableToggle label={`Cost build-up lines and final offer price ${money(offer)}. Subtotals may overlap; do not sum all lines.`} headers={['Step', 'Value', 'Formula']} rows={rows}>
    <div className="waterfall-chart cost-driver-chart" aria-label={`Cost build-up ending at ${money(offer)}`}>
      {visible.map(step => <div className="cost-driver-row" key={step.key}>
        <div><span>{step.label}</span><strong>{money(step.amount_chf)}</strong></div>
        <div className="hbar-track"><i style={{ width: `${Math.abs(Number(step.amount_chf)) / max * 100}%`, background: Number(step.amount_chf) < 0 ? 'var(--viz-highlight)' : 'var(--viz-accent)' }} /></div>
        <small>{step.formula}</small>
      </div>)}
      <div className="cost-driver-totals"><div><span>Cost baseline</span><strong>{money(baseline)}</strong></div><div><span>Final offer price</span><strong>{money(offer)}</strong></div></div>
      <p className="chart-legend">Build-up lines can include subtotals. Totals above are calculated from the saved estimate.</p>
    </div>
  </ChartTableToggle>;
}
