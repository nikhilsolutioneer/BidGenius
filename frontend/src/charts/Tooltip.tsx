import { useId, useState } from 'react';

export type ChartDatum = {
  id: string;
  label: string;
  value: string;
  formula?: string;
  source?: string;
};

export function useChartTooltip() {
  const id = useId();
  const [tip, setTip] = useState<(ChartDatum & { x: number; y: number }) | null>(null);
  return {
    id,
    tip,
    show: (item: ChartDatum, x: number, y: number) => setTip({ ...item, x, y }),
    hide: () => setTip(null),
  };
}

export function Tooltip({ id, tip }: { id: string; tip: (ChartDatum & { x: number; y: number }) | null }) {
  if (!tip) return null;
  return (
    <div id={id} role="tooltip" className="chart-tooltip" style={{ left: tip.x, top: tip.y }}>
      <strong>{tip.label}: {tip.value}</strong>
      {tip.formula && <span>{tip.formula}</span>}
      {tip.source && <small>{tip.source}</small>}
    </div>
  );
}
