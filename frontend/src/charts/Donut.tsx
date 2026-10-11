import { ChartTableToggle } from './ChartTableToggle';

export function Donut({ title, note, items, unit }: { title: string; note: string; items: { label: string; value: number; formatted: string }[]; unit: string }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  let offset = 0;
  const colors = ['var(--viz-accent)', 'var(--viz-highlight)', 'var(--viz-context)'];
  return <ChartTableToggle label={`${title}. ${note}`} headers={['Category', unit, 'Share']} rows={items.map(item => [item.label, item.formatted, total ? `${(item.value / total * 100).toFixed(1)}%` : '—'])}>
    <div className="donut-chart">
      <svg viewBox="0 0 260 220" role="img" aria-label={`${title}: ${items.map(item => `${item.label} ${item.formatted}`).join(', ')}`}>
        <circle cx="130" cy="110" r="78" fill="none" stroke="var(--bg)" strokeWidth="30" />
        {items.map((item, index) => {
          const share = total > 0 ? item.value / total * 100 : 0;
          const start = offset; offset += share;
          return <circle key={item.label} cx="130" cy="110" r="78" fill="none" stroke={colors[index % colors.length]} strokeWidth="30" pathLength="100" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} transform="rotate(-90 130 110)"><title>{item.label}: {item.formatted} ({share.toFixed(1)}%)</title></circle>;
        })}
        <text x="130" y="108" textAnchor="middle" className="donut-center">{total ? `${(items[0].value / total * 100).toFixed(1)}%` : '—'}</text>
        <text x="130" y="132" textAnchor="middle">{items[0]?.label || 'No data'}</text>
      </svg>
      <div className="donut-legend">{items.map((item, index) => <div key={item.label}><i style={{ background: colors[index % colors.length] }} /><span>{item.label}</span><strong>{item.formatted}</strong></div>)}</div>
      <p>{note}</p>
    </div>
  </ChartTableToggle>;
}
