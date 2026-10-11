import { useEffect, useState } from 'react';
import { api, money } from '../api';
import { ChartTableToggle } from './ChartTableToggle';
import { Tooltip, useChartTooltip } from './Tooltip';

export type SensitivityItem = { key: string; label: string; group: string; field: string; step: string; down_delta_chf: string; up_delta_chf: string; formula?: string; source?: string };

export function Tornado({ projectId, revision, onOpenControl }: { projectId: string; revision: number; onOpenControl: (field: string) => void }) {
  const [items, setItems] = useState<SensitivityItem[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const tip = useChartTooltip();
  useEffect(() => {
    let live = true;
    setLoading(true); setFailed(false);
    api<{ items: SensitivityItem[] }>(`/projects/${projectId}/sensitivity`, { method: 'POST', body: JSON.stringify({ revision }) })
      .then((result) => { if (live) setItems(result.items); })
      .catch(() => { if (live) { setItems([]); setFailed(true); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [projectId, revision, attempt]);
  const shown = showAll ? items : items.slice(0, 5);
  const max = Math.max(...shown.flatMap((item) => [Math.abs(Number(item.down_delta_chf)), Math.abs(Number(item.up_delta_chf))]), 1);
  return (
    <ChartTableToggle label="Which assumption moves the price. Offer-price deltas around zero." headers={['Assumption', 'Down step', 'Up step']} rows={items.map((item) => [item.label, money(item.down_delta_chf), money(item.up_delta_chf)])}>
      <div className="tornado-chart" role="group" aria-label="Which assumption moves the price">
        {loading && <p role="status">Calculating price sensitivity…</p>}
        {failed && <div role="alert">Price sensitivity could not be loaded. <button type="button" className="text-btn" onClick={() => setAttempt(value => value + 1)}>Retry</button></div>}
        {!loading && !failed && items.length === 0 && <p>No sensitivity results are available for this revision.</p>}
        {shown.map((item) => {
          const left = Math.abs(Number(item.down_delta_chf)) / max * 45;
          const right = Math.abs(Number(item.up_delta_chf)) / max * 45;
          const datum = { id: item.key, label: item.label, value: `${money(item.down_delta_chf)} / ${money(item.up_delta_chf)}`, formula: item.formula, source: item.source };
          return (
            <button key={item.key} className="tornado-row" onClick={() => onOpenControl(item.field)} onFocus={(e) => tip.show(datum, e.currentTarget.getBoundingClientRect().left, e.currentTarget.getBoundingClientRect().top)} onBlur={tip.hide}>
              <span>{item.label}</span>
              <i className="tornado-left" style={{ width: `${left}%` }} onMouseMove={(e) => tip.show(datum, e.clientX, e.clientY)} onMouseLeave={tip.hide} />
              <b />
              <i className="tornado-right" style={{ width: `${right}%` }} onMouseMove={(e) => tip.show(datum, e.clientX, e.clientY)} onMouseLeave={tip.hide} />
              <strong>{money(item.down_delta_chf)} / {money(item.up_delta_chf)}</strong>
            </button>
          );
        })}
        {items.length > 5 && <button className="show-more" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Show top 5' : `Show all ${items.length}`}</button>}
        <Tooltip id={tip.id} tip={tip.tip} />
      </div>
    </ChartTableToggle>
  );
}
