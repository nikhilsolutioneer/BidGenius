import { money, probabilityPercent } from '../api';
import type { Scenario } from '../types';
import { ChartTableToggle } from './ChartTableToggle';
import { Tooltip, useChartTooltip } from './Tooltip';

type CurvePoint = { price_chf: string; estimated_win_probability: string; achieved_margin_pct: string; expected_contribution_chf: string };

export function CurveWithPoints({ curve, scenarios, selected }: { curve: CurvePoint[]; scenarios: Scenario[]; selected?: string }) {
  const tip = useChartTooltip();
  if (!curve.length || !scenarios.length) {
    return <div className="curve-chart text-muted">Scenario curve is not available for this revision.</div>;
  }
  const prices = [...curve.map((p) => Number(p.price_chf)), ...scenarios.map((s) => Number(s.bid_price_chf))];
  const minX = Math.min(...prices);
  const maxX = Math.max(...prices);
  const x = (value: string) => 34 + ((Number(value) - minX) / Math.max(maxX - minX, 1)) * 330;
  const y = (value: string) => 166 - Number(value) * 120;
  const d = curve.map((point, index) => `${index ? 'L' : 'M'} ${x(point.price_chf)} ${y(point.estimated_win_probability)}`).join(' ');
  return (
    <ChartTableToggle label="Price vs illustrative win probability. Each price uses its strategy margin." headers={['Point', 'Price', 'Margin', 'Win probability', 'Expected contribution']} rows={scenarios.map((s) => [s.scenario, money(s.bid_price_chf), `${s.margin_pct}%`, `${probabilityPercent(s.estimated_win_probability)}%`, money(s.expected_contribution_chf)])}>
      <div className="curve-chart" aria-label="Price versus illustrative win probability">
        <svg viewBox="0 0 400 205" role="img" aria-label="Price versus illustrative win probability curve.">
          <title>Price versus illustrative win probability</title>
          <line x1="34" y1="166" x2="372" y2="166" className="chart-axis" />
          <line x1="34" y1="36" x2="34" y2="166" className="chart-axis" />
          {[0, 0.5, 1].map(value => <text key={value} x="28" y={y(String(value)) + 3} textAnchor="end">{value * 100}%</text>)}
          <text x="34" y="188" textAnchor="start">{money(String(minX))}</text>
          <text x="372" y="188" textAnchor="end">{money(String(maxX))}</text>
          <path d={d} fill="none" stroke="var(--viz-context)" strokeWidth="2" />
          {scenarios.map((scenario) => {
            const active = selected === scenario.scenario;
            const datum = { id: scenario.scenario, label: scenario.scenario, value: `${money(scenario.bid_price_chf)} · ${scenario.margin_pct}% margin · ${probabilityPercent(scenario.estimated_win_probability)}% win probability`, formula: 'scenario heuristic sampled by backend', source: 'project_parameters.stretch_bid_optimization' };
            return (
              <g key={scenario.scenario}>
                <circle tabIndex={0} aria-describedby={tip.id} cx={x(scenario.bid_price_chf)} cy={y(scenario.estimated_win_probability)} r={active ? 6 : 5} fill={active ? 'var(--viz-highlight)' : 'var(--viz-context)'}
                  onMouseMove={(e) => tip.show(datum, e.clientX, e.clientY)} onMouseLeave={tip.hide} onFocus={(e) => tip.show(datum, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top)} onBlur={tip.hide} />
                <text x={x(scenario.bid_price_chf)} y={y(scenario.estimated_win_probability) - 10} textAnchor="middle">{scenario.scenario}</text>
              </g>
            );
          })}
        </svg>
        <small>Illustrative heuristic from project parameters - not a calibrated prediction.</small>
        <Tooltip id={tip.id} tip={tip.tip} />
      </div>
    </ChartTableToggle>
  );
}
