import type { ReactNode } from 'react';
import { useState } from 'react';
import { Modal } from '../components';

export function ChartTableToggle({
  label,
  headers,
  rows,
  children,
}: {
  label: string;
  headers: string[];
  rows: (string | number)[][];
  children: ReactNode;
}) {
  const [table, setTable] = useState(false);
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="chart-wrap">
      <div className="chart-actions">
        <button type="button" className="chart-table-toggle" onClick={() => { setTable(true); setExpanded(true); }}>View data</button>
        <button type="button" className="chart-table-toggle" onClick={() => { setTable(false); setExpanded(true); }} aria-label="Expand chart">Expand ↗</button>
      </div>
      {!expanded && children}
      <Modal open={expanded} onClose={() => setExpanded(false)} title="Expanded view" description={label} wide>
        <div className="chart-expanded">
          <div className="chart-actions">
            <button type="button" className="chart-table-toggle" aria-pressed={!table} onClick={() => setTable(false)}>Chart</button>
            <button type="button" className="chart-table-toggle" aria-pressed={table} onClick={() => setTable(true)}>Table</button>
          </div>
          {table ? (
        <div className="table-scroll chart-table" role="region" aria-label={label}>
          <table className="data-table">
            <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
            <tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
          ) : children}
        </div>
      </Modal>
    </div>
  );
}
