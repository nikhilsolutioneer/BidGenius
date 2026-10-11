import { money } from '../api';
import { ChartTableToggle } from './ChartTableToggle';
import { Tooltip, useChartTooltip } from './Tooltip';

export function StackedRangeBar({
  priced,
  low,
  median,
  high,
}: {
  priced: string;
  low: string;
  median: string;
  high: string;
}) {
  const tip = useChartTooltip();
  const p = Number(priced);
  const med = Number(median);
  const hi = Number(high);
  const total = Math.max(p + hi, 1);
  // The viewBox is 400px wide between x=10 and x=410. Keep all geometry in
  // that same coordinate system; mixing percentages with SVG pixels caused
  // the median marker to render beyond the visible bar for large estimates.
  const chartWidth = 400;
  const pricedW = (p / total) * chartWidth;
  const rangeW = (hi / total) * chartWidth;
  const medianX = ((p + med) / total) * chartWidth;
  const pricedDatum = { id: 'priced', label: 'Priced included scope', value: money(priced), formula: 'included-scope selling price', source: 'summary.totals.selling_price_chf' };
  const rangeDatum = { id: 'range', label: 'Unpriced benchmark exposure', value: `+${money(low)} to +${money(high)}`, formula: 'allowance low to high; commercial assumptions are applied separately', source: 'summary.completeness.allowance_*' };
  return (
    <ChartTableToggle label={`Exposure chart. Included selling price ${money(priced)} and unpriced benchmark exposure ${money(low)} to ${money(high)}. Commercial assumptions are applied separately.`} headers={['Segment', 'Value']} rows={[['Included selling price', money(priced)], ['Exposure low', money(low)], ['Exposure median', money(median)], ['Exposure high', money(high)]]}>
      <div className="price-confidence-chart" aria-label={`Price confidence. Priced ${money(priced)}. Unpriced range ${money(low)} to ${money(high)}.`}>
        <svg viewBox="0 0 420 76" role="img" aria-label={`Exposure chart: included selling price ${money(priced)} plus benchmark exposure ${money(low)} to ${money(high)}. Commercial assumptions are applied separately.`}>
          <title>Included price and benchmark exposure</title>
          <defs>
            <pattern id="viz-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="7" height="7" fill="var(--viz-range-fill)" />
              <line x1="0" y1="0" x2="0" y2="7" stroke="var(--viz-range-hatch)" strokeWidth="2" />
            </pattern>
          </defs>
          <line x1="10" y1="48" x2="410" y2="48" className="chart-axis" />
          <rect tabIndex={0} aria-describedby={tip.id} x="10" y="24" width={Math.max(2, pricedW)} height="20" rx="4" fill="var(--viz-accent)"
            onMouseMove={(e) => tip.show(pricedDatum, e.clientX, e.clientY)} onMouseLeave={tip.hide} onFocus={(e) => tip.show(pricedDatum, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top)} onBlur={tip.hide} />
          <rect tabIndex={0} aria-describedby={tip.id} x={10 + pricedW + 2} y="24" width={Math.max(2, rangeW - 2)} height="20" rx="4" fill="url(#viz-hatch)"
            onMouseMove={(e) => tip.show(rangeDatum, e.clientX, e.clientY)} onMouseLeave={tip.hide} onFocus={(e) => tip.show(rangeDatum, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top)} onBlur={tip.hide} />
          <line x1={10 + medianX} y1="18" x2={10 + medianX} y2="51" stroke="var(--viz-highlight)" strokeWidth="2" />
        </svg>
        <div className="chart-legend"><span>Included selling price {money(priced)}</span><span>Benchmark exposure +{money(low)}–{money(high)}</span></div>
      </div>
      <Tooltip id={tip.id} tip={tip.tip} />
    </ChartTableToggle>
  );
}
