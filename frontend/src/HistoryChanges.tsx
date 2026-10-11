import { label, money } from './api';
import type { History } from './types';

type Change = { name: string; before: string; after: string };
const hidden = new Set(['id', 'document_id', 'source_span_ids', 'field_sources', 'candidates', 'warnings', 'attributes']);
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const display = (value: unknown, key: string): string => {
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (Array.isArray(value)) return value.every((item) => typeof item === 'string') ? value.join(' · ') : `${value.length} entries`;
  if (record(value)) return 'Recorded details';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return key.endsWith('_chf') && /^-?\d+(?:\.\d+)?$/.test(String(value)) ? money(value, 2) : String(value);
};
const changesBetween = (before: unknown, after: unknown, path: string[] = []): Change[] => {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (record(before) || record(after)) {
    const oldFields = record(before) ? before : {};
    const newFields = record(after) ? after : {};
    return [...new Set([...Object.keys(oldFields), ...Object.keys(newFields)])]
      .filter((key) => !hidden.has(key) && !key.startsWith('_'))
      .flatMap((key) => changesBetween(oldFields[key], newFields[key], [...path, key]));
  }
  const key = path.at(-1) || 'Value';
  return [{ name: path.map(label).join(' › '), before: display(before, key), after: display(after, key) }];
};

export const historyTarget = (decision: History): string => {
  if (decision.entity_type === 'assumptions') return 'Project assumptions';
  if (decision.entity_type === 'commercial') return 'Commercial context';
  const value = record(decision.new_value) ? decision.new_value : record(decision.old_value) ? decision.old_value : {};
  return String(value.reference || value.title || label(decision.entity_type));
};

export default function HistoryChanges({ decision }: { decision: History }) {
  const changes = changesBetween(decision.old_value, decision.new_value);
  return <div className="audit-list">
    {changes.length ? changes.map((change, index) => <div key={`${change.name}-${index}`}>
      <strong>{change.name}</strong>
      <span>{change.before} → {change.after}</span>
    </div>) : <div>No displayed fields changed. Full revision data is available in the JSON export.</div>}
  </div>;
}
