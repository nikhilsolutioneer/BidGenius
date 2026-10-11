import { label, money } from '../api';
import { missingCauseLabels } from '../coverage';
import { ChartTableToggle } from './ChartTableToggle';
import { Tooltip, useChartTooltip } from './Tooltip';

export type HBarItem = { cause: string; count: number; stake_chf: string; formula?: string; source?: string };

export function HBar({ items, onCause }: { items: HBarItem[]; onCause: (cause: string) => void }) {
  const tip = useChartTooltip();
  const max = Math.max(...items.map((item) => Number(item.stake_chf)), 1);
  return (
    <ChartTableToggle label="CHF at stake by review cause. Causes may overlap." headers={['Cause', 'CHF at stake', 'Positions']} rows={items.map((item) => [missingCauseLabels[item.cause] || label(item.cause), money(item.stake_chf), item.count])}>
      <div className="hbar-chart" aria-label="CHF at stake by review cause">
        {items.map((item, index) => {
          const width = `${Math.max(3, (Number(item.stake_chf) / max) * 100)}%`;
          const datum = { id: item.cause, label: missingCauseLabels[item.cause] || label(item.cause), value: `${money(item.stake_chf)} · ${item.count} positions`, formula: item.formula, source: item.source || 'summary.review_cause_stakes' };
          return (
            <button key={item.cause} className="hbar-row" onClick={() => onCause(item.cause)} onFocus={(e) => tip.show(datum, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top)} onBlur={tip.hide}>
              <span>{datum.label}<small>{item.count} positions</small></span>
              <span className="hbar-track" onMouseMove={(e) => tip.show(datum, e.clientX, e.clientY)} onMouseLeave={tip.hide}>
                <i className={`seq-${Math.min(6, index + 1)}`} style={{ width }} />
              </span>
              <strong>{money(item.stake_chf)}</strong>
            </button>
          );
        })}
        <Tooltip id={tip.id} tip={tip.tip} />
      </div>
    </ChartTableToggle>
  );
}
