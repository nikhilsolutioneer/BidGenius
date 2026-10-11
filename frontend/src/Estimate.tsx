import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type { ColumnDef, Row, SortingState } from '@tanstack/react-table';
import {
  ArrowDownUp,
  Check,
  ChevronLeft,
  ChevronRight,
  Columns3,
  FileSearch,
  FileText,
  Filter,
  History as HistoryIcon,
  Layers,
  Pencil,
  Search,
  ShieldCheck,
  Undo2,
  X,
  Calculator,
  ExternalLink,
  AlertTriangle,
} from 'lucide-react';
import { Badge, Button, DetailRow, Empty, Spinner, Status, Modal, Field, ErrorBox } from './components';
import { compareDecimal, date, humanEvidence, label, money, number, post } from './api';
import { missingCauses, missingCauseLabels } from './coverage';
import PositionProposals from './PositionProposals';
import HistoryChanges from './HistoryChanges';
import type { Mutate } from './Dialogs';
import type { Document, History, Position, References, SourceSpan } from './types';
const PdfViewer = lazy(() => import('./PdfViewer'));
const systemNames: Record<string, string> = {
  LA01: 'Ancillary rooms',
  LA02: 'Dining rooms',
  LA03: 'Kitchen',
  LA04: 'Classrooms',
  LA05: 'Sports hall',
  ROOF: 'Rooftop supports',
  Unassigned: 'Unassigned scope',
};
export default function Estimate({
  positions,
  document,
  projectId,
  revision,
  selectedId,
  onSelect,
  onEdit,
  onAccept,
  onManual,
  onUndo,
  onBulkAreaRule,
  history,
  references,
  sourcePage,
  mutate,
  initialCause,
}: {
  positions: Position[];
  document: Document;
  projectId: string;
  revision: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onEdit: (p: Position) => void;
  onAccept: (p: Position) => void;
  onManual: (spans: SourceSpan[]) => void;
  onUndo: (h: History) => void;
  onBulkAreaRule: (count: number, reason: string) => Promise<unknown>;
  history: History[];
  references: References | null;
  sourcePage: number | null;
  mutate: Mutate;
  initialCause?: string;
}) {
  const [search, setSearch] = useState('');
  const [system, setSystem] = useState('all');
  const [needsReview, setNeedsReview] = useState(false);
  const [status, setStatus] = useState('all');
  const [missingCause, setMissingCause] = useState(initialCause || 'all');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [tab, setTab] = useState<'source' | 'calculation' | 'history'>('calculation');
  const [extra, setExtra] = useState(false);
  const [inspectorWidth, setInspectorWidth] = useState(500);
  const [density, setDensity] = useState<'compact' | 'comfortable'>(() => (localStorage.getItem('estimate-density') as 'compact' | 'comfortable') || 'compact');
  const [areaDialogOpen, setAreaDialogOpen] = useState(false);
  const [areaRows, setAreaRows] = useState<{ id: string; reference: string; description: string; material_delta_chf: string; labour_delta_chf: string; direct_delta_chf: string; hours_delta: string }[]>([]);
  const [areaPreviewLoading, setAreaPreviewLoading] = useState(false);
  const [areaPreviewError, setAreaPreviewError] = useState('');
  const [areaSaveError, setAreaSaveError] = useState('');
  const [areaReason, setAreaReason] = useState('');
  const isHighImpactUnpriced = (p: Position) => {
    const isUnpriced = p.cost?.direct_cost_chf === null || p.cost?.direct_cost_chf === undefined;
    return (
      isUnpriced &&
      (['Equipment', 'Supplier packages'].includes(p.category) ||
        p.pricing_basis === 'supplier_reference' ||
        p.status === 'supplier_quote_required' ||
        p.id.startsWith('PKG-'))
    );
  };

  const filtered = useMemo(
    () => {
      const list = positions.filter(
        (p) =>
          (system === 'all' || p.system === system) &&
          (status === 'all' || p.status === status) &&
          (missingCause === 'all' || missingCauses(p).includes(missingCause)) &&
          (!needsReview || p.review_state !== 'accepted'),
      );
      // Default sort when no manual table sort is active:
      // 1. High-impact unpriced items ("Needs a price") first
      // 2. Priced items descending by direct cost
      // 3. Other unpriced items
      if (sorting.length === 0) {
        return [...list].sort((a, b) => {
          const aHigh = isHighImpactUnpriced(a);
          const bHigh = isHighImpactUnpriced(b);
          if (aHigh && !bHigh) return -1;
          if (!aHigh && bHigh) return 1;
          const aCost = a.cost?.direct_cost_chf ?? null;
          const bCost = b.cost?.direct_cost_chf ?? null;
          if (aCost !== null && bCost !== null) return -compareDecimal(aCost, bCost);
          if (aCost !== null && bCost === null) return -1;
          if (aCost === null && bCost !== null) return 1;
          return (a.source_page || 0) - (b.source_page || 0);
        });
      }
      return list;
    },
    [positions, system, status, needsReview, missingCause, sorting],
  );
  const selected = positions.find((p) => p.id === selectedId) || null;
  useEffect(() => { localStorage.setItem('estimate-density', density); }, [density]);
  const areaRuleCount = positions.filter(
    (p) =>
      p.category === 'Ductwork' &&
      p.install_code === 'DUCT_RECT' &&
      p.unit === 'm2' &&
      !p.product_id &&
      p.attributes.schedule_code === 'L' &&
      p.attributes.width_mm &&
      p.attributes.height_mm,
  ).length;
  const openAreaRuleDialog = async () => {
    setAreaDialogOpen(true);
    setAreaRows([]);
    setAreaReason('');
    setAreaPreviewError('');
    setAreaPreviewLoading(true);
    try {
      const result = await post<{ revision: number; affected_positions?: typeof areaRows }>(`/projects/${projectId}/what-if/preview`, {
        expected_revision: revision,
        changes: { duct_pricing: { rect_duct_area_rate_enabled: 'true' } },
        include_positions: true,
      });
      setAreaRows(result.affected_positions || []);
    } catch (error) {
      setAreaPreviewError((error as Error).message);
    } finally {
      setAreaPreviewLoading(false);
    }
  };
  const columns = useMemo<ColumnDef<Position>[]>(
    () => [
      {
        id: 'position',
        header: 'Position / description',
        accessorFn: (p) => `${p.reference || ''} ${p.id} ${p.description} ${p.product_id || ''}`,
        cell: ({ row }) => (
          <button
            className="position-link"
            title={row.original.description}
            onClick={() => {
              onSelect(row.original.id);
              setTab('calculation');
            }}
          >
            <span className="row-id">
              <span>{row.original.reference || `${row.original.system} · p.${row.original.source_page}`}</span>
              {row.original.origin === 'manual' && <Badge tone="blue">Added</Badge>}
            </span>
            <strong>{row.original.description}</strong>
            {row.original.product_id && (
              <small>
                {row.original.product_id} · {label(row.original.pricing_basis)}
              </small>
            )}
          </button>
        ),
      },
      {
        accessorKey: 'quantity',
        header: 'Quantity',
        cell: ({ row }) => (
          <span className="quantity-cell">
            {row.original.quantity === null ? (
              <span className="text-muted">Unknown</span>
            ) : (
              <>
                {number(row.original.quantity, 3)} <small>{row.original.unit}</small>
              </>
            )}
          </span>
        ),
      },
      ...(extra
        ? [
            {
              id: 'material',
              header: 'Material',
              accessorFn: (p: Position) => p.cost?.material_cost_chf,
              sortingFn: (a: Row<Position>, b: Row<Position>) => compareDecimal(a.original.cost?.material_cost_chf, b.original.cost?.material_cost_chf),
              cell: ({ row }: { row: { original: Position } }) =>
                money(row.original.cost?.material_cost_chf, 2),
            },
            {
              id: 'labour',
              header: 'Labour',
              accessorFn: (p: Position) => p.cost?.labour_cost_chf,
              sortingFn: (a: Row<Position>, b: Row<Position>) => compareDecimal(a.original.cost?.labour_cost_chf, b.original.cost?.labour_cost_chf),
              cell: ({ row }: { row: { original: Position } }) =>
                money(row.original.cost?.labour_cost_chf, 2),
            },
          ]
        : []),
      {
        id: 'cost',
        header: 'Direct cost',
        accessorFn: (p) => p.cost?.direct_cost_chf,
        sortingFn: (a, b) => compareDecimal(a.original.cost?.direct_cost_chf, b.original.cost?.direct_cost_chf),
        cell: ({ row }) => (
          <span className={`cost-cell ${row.original.cost?.direct_cost_chf === null ? 'text-muted' : ''}`}>
            {row.original.pricing_basis === 'included_elsewhere' ? 'Covered elsewhere' : money(row.original.cost?.direct_cost_chf, 2)}
            {row.original.pricing_basis === 'supplier_reference' && <small className="partial-cost">Provisional · supplier quote needed</small>}
            {row.original.cost?.direct_cost_chf == null &&
              (row.original.cost?.material_cost_chf != null ||
                row.original.cost?.labour_cost_chf != null) && (
                <small className="partial-cost">
                  Known:{' '}
                  {row.original.cost?.material_cost_chf != null
                    ? `material ${money(row.original.cost.material_cost_chf, 2)}`
                    : ''}
                  {row.original.cost?.material_cost_chf != null && row.original.cost?.labour_cost_chf != null
                    ? ' · '
                    : ''}
                  {row.original.cost?.labour_cost_chf != null
                    ? `labour ${money(row.original.cost.labour_cost_chf, 2)}`
                    : ''}
                </small>
              )}
          </span>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Outcome',
        cell: ({ row }) => (
          <div className="status-cell">
            <Status status={row.original.status} />
            {row.original.review_state === 'accepted' && (
              <small className="text-green">
                <Check size={11} /> Reviewed
              </small>
            )}
          </div>
        ),
      },
      {
        id: 'source',
        header: 'Source',
        cell: ({ row }) => (
          <button
            className="source-chip"
            onClick={() => {
              onSelect(row.original.id);
              setTab('source');
            }}
            aria-label={`View source page ${row.original.source_page}`}
          >
            <FileText size={13} /> {row.original.source_page}
          </button>
        ),
      },
    ],
    [onSelect, extra],
  );
  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
    globalFilterFn: 'includesString',
  });
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
      const rows = table.getFilteredRowModel().rows;
      if (event.key === 'Escape' && selectedId) { onSelect(null); return; }
      if (event.key === 'Enter' && !selectedId && rows.length) { onSelect(rows[table.getState().pagination.pageIndex * 50]?.original.id || rows[0].original.id); return; }
      const current = rows.findIndex((row) => row.original.id === selectedId);
      if (['j', 'ArrowDown', 'k', 'ArrowUp'].includes(event.key) && rows.length) {
        event.preventDefault();
        const next = Math.max(0, Math.min(rows.length - 1, (current < 0 ? 0 : current) + (event.key === 'j' || event.key === 'ArrowDown' ? 1 : -1)));
        table.setPageIndex(Math.floor(next / 50)); onSelect(rows[next].original.id);
      }
      if (event.key.toLowerCase() === 'a' && selected && selected.review_state !== 'accepted') onAccept(selected);
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [table, selectedId, selected, onSelect, onAccept]);
  const systems = Array.from(new Set(positions.map((p) => p.system))).sort();
  const showInspector = Boolean(selected || sourcePage);
  return (
    <div className={`estimate-page density-${density}`}>
      <div className="estimate-heading">
        <div>
          <div className="eyebrow">ESTIMATE WORKSPACE</div>
          <h1>Inspect. Decide. Defend.</h1>
          <p>{positions.length} positions · original evidence always one click away</p>
        </div>
        <Button
          onClick={() => {
            onSelect(null);
            setTab('source');
          }}
          disabled={!showInspector}
        >
          <X size={15} /> Close inspector
        </Button>
      </div>
      <div
        className={`estimate-layout ${showInspector ? 'with-inspector' : ''}`}
        style={{ '--inspector-width': `${inspectorWidth}px` } as React.CSSProperties}
      >
        <aside className="systems-nav">
          <div className="section-label">VENTILATION SYSTEMS</div>
          <button className={system === 'all' ? 'active' : ''} onClick={() => setSystem('all')}>
            <Layers size={16} />
            <span>All systems</span>
            <b>{positions.length}</b>
          </button>
          {systems.map((s) => (
            <button key={s} className={system === s ? 'active' : ''} onClick={() => setSystem(s)}>
              <span className="system-code">{s}</span>
              <span>{systemNames[s] || s}</span>
              <b>{positions.filter((p) => p.system === s).length}</b>
            </button>
          ))}
          <div className="systems-note">
            <ShieldCheck size={21} />
            <strong>Evidence stays attached.</strong>
            <p>Review a position to see its source, calculation, and decision history.</p>
          </div>
        </aside>
        <section className="estimate-table-panel">
          <div className="table-toolbar">
            <label className="search-input">
              <Search size={16} />
              <input
                aria-label="Search estimate"
                placeholder="Search positions, products…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button aria-label="Clear search" onClick={() => setSearch('')}>
                  <X size={13} />
                </button>
              )}
            </label>
            <button
              className={`filter-btn ${needsReview ? 'selected' : ''}`}
              onClick={() => setNeedsReview((v) => !v)}
              aria-pressed={needsReview}
            >
              <Filter size={14} /> Needs review
            </button>
            <div className="density-toggle" role="group" aria-label="Table density">
              <button className={density === 'compact' ? 'active' : ''} onClick={() => setDensity('compact')}>Compact</button>
              <button className={density === 'comfortable' ? 'active' : ''} onClick={() => setDensity('comfortable')}>Comfortable</button>
            </div>
            {areaRuleCount > 0 && (
              <Button onClick={openAreaRuleDialog}>
                Apply area-rate rule to {areaRuleCount} rows
              </Button>
            )}
            <button
              className={`icon-btn ${extra ? 'selected' : ''}`}
              onClick={() => setExtra((v) => !v)}
              aria-pressed={extra}
              title="Show material and labour columns"
              aria-label="Toggle detailed columns"
            >
              <Columns3 size={17} />
            </button>
          </div>
          <div className="table-subtoolbar">
            <span>
              {table.getFilteredRowModel().rows.length} positions{system !== 'all' && ` in ${system}`}
            </span>
            <label className="inline">
              <span>Review cause</span>
              <select
                aria-label="Filter review cause"
                value={missingCause}
                onChange={(e) => setMissingCause(e.target.value)}
              >
                <option value="all">All causes</option>
                {Object.entries(missingCauseLabels).map(([key, title]) => (
                  <option key={key} value={key}>
                    {title} ({positions.filter((p) => missingCauses(p).includes(key)).length})
                  </option>
                ))}
              </select>
            </label>
            <label className="inline">
              <span>Outcome</span>
              <select aria-label="Filter outcome" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">All outcomes</option>
                {Array.from(new Set(positions.map((p) => p.status)))
                  .sort()
                  .map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className="table-scroll estimate-table-scroll">
            <table className="data-table estimate-table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th key={h.id}>
                        {h.column.getCanSort() ? (
                          <button className="sort-button" onClick={h.column.getToggleSortingHandler()}>
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            <ArrowDownUp size={11} />
                          </button>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className={row.original.id === selectedId ? 'row-selected' : ''}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {table.getFilteredRowModel().rows.length === 0 && (
              <Empty icon={<FileSearch size={32} />} title="No positions match">
                Try another search or clear the filters.
              </Empty>
            )}
          </div>
          <div className="pagination">
            <span>
              {table.getState().pagination.pageIndex * 50 + 1}–{Math.min((table.getState().pagination.pageIndex + 1) * 50, table.getFilteredRowModel().rows.length)} of {table.getFilteredRowModel().rows.length}
            </span>
            <small className="shortcut-hint">j/k or ↑/↓ select · Enter inspect · Esc close · a accept review</small>
            <div className="inline">
              <Button
                disabled={!table.getCanPreviousPage()}
                onClick={() => table.previousPage()}
                aria-label="Previous positions page"
              >
                <ChevronLeft size={15} />
              </Button>
              <Button
                disabled={!table.getCanNextPage()}
                onClick={() => table.nextPage()}
                aria-label="Next positions page"
              >
                <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        </section>
        {showInspector && (
          <aside className="inspector">
            <div className="inspector-head">
              <div>
                <div className="section-label">EVIDENCE INSPECTOR</div>
                <h3>{selected?.reference || selected?.id || `Source page ${sourcePage}`}</h3>
              </div>
              <button
                className="icon-btn"
                aria-label="Close evidence inspector"
                onClick={() => onSelect(null)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="inspector-tabs">
              {(['source', 'calculation', 'history'] as const).map((t) => (
                <button
                  key={t}
                  className={(selected ? tab : 'source') === t ? 'active' : ''}
                  onClick={() => setTab(t)}
                  disabled={!selected && t !== 'source'}
                >
                  {t === 'source' ? (
                    <FileText size={14} />
                  ) : t === 'calculation' ? (
                    <Calculator size={14} />
                  ) : (
                    <HistoryIcon size={14} />
                  )}{' '}
                  {label(t)}
                </button>
              ))}
            </div>
            <label className="inspector-size">
              <span>Inspector width</span>
              <input
                type="range"
                min="330"
                max="640"
                step="10"
                value={inspectorWidth}
                onChange={(e) => setInspectorWidth(Number(e.target.value))}
              />
            </label>
            <div className="inspector-content">
              {tab === 'source' || !selected ? (
                <Suspense fallback={<Spinner text="Loading source viewer…" />}>
                  <PdfViewer
                    document={document}
                    page={sourcePage || selected?.source_page || 1}
                    highlightIds={selected?.source_span_ids || []}
                    onCreate={onManual}
                  />
                </Suspense>
              ) : tab === 'calculation' ? (
                <Calculation position={selected} references={references} mutate={mutate} />
              ) : (
                <div className="position-history">
                  {history.filter((h) => h.entity_id === selected.id).length === 0 ? (
                    <Empty icon={<HistoryIcon size={26} />} title="The original extraction">
                      No estimator changes have been recorded for this position.
                    </Empty>
                  ) : (
                    history
                      .filter((h) => h.entity_id === selected.id)
                      .slice()
                      .reverse()
                      .map((h) => (
                        <div className="history-entry" key={h.id}>
                          <div className="inline">
                            <Badge tone="blue">Revision {h.revision}</Badge>
                            <small>{date(h.timestamp)}</small>
                          </div>
                          <h4>{h.reason}</h4>
                          <p>{h.actor}</p>
                          <DetailRow name="Price change">{money(h.price_delta_chf, 2)}</DetailRow>
                          <details>
                            <summary>Inspect before / after</summary>
                            <HistoryChanges decision={h} />
                          </details>
                          <Button variant="ghost" onClick={() => onUndo(h)}>
                            <Undo2 size={14} /> Reverse this change
                          </Button>
                        </div>
                      ))
                  )}
                </div>
              )}
            </div>
            {selected && (
              <div className="inspector-actions">
                <Button onClick={() => onEdit(selected)}>
                  <Pencil size={15} /> Edit
                </Button>
                <Button
                  variant="primary"
                  disabled={selected.review_state === 'accepted'}
                  onClick={() => onAccept(selected)}
                >
                  <Check size={15} />
                  {selected.review_state === 'accepted' ? 'Reviewed' : 'Accept review'}
                </Button>
              </div>
            )}
          </aside>
        )}
      </div>
      <Modal
        open={areaDialogOpen}
        onClose={() => setAreaDialogOpen(false)}
        title={`Apply area-rate rule to ${areaRuleCount} rows?`}
        description="Review each affected position’s direct-cost impact. Section fittings remain unpriced. This is a reversible decision."
        wide
      >
        <div className="modal-body">
          {areaPreviewError && <ErrorBox message={areaPreviewError} />}
          {areaSaveError && <ErrorBox message={areaSaveError} />}
          {areaPreviewLoading ? <Spinner text="Calculating row-by-row price impact…" /> : (
            <div className="table-scroll bulk-impact-list">
              <table className="data-table">
                <thead><tr><th>Position</th><th>Description</th><th>Material Δ</th><th>Labour Δ</th><th>Direct-cost impact</th><th>Hours Δ</th></tr></thead>
                <tbody>{areaRows.map((row) => <tr key={row.id}>
                  <td>{row.reference}</td><td>{row.description}</td>
                  <td className="numeric">{money(row.material_delta_chf, 2)}</td>
                  <td className="numeric">{money(row.labour_delta_chf, 2)}</td>
                  <td className="numeric"><strong>{money(row.direct_delta_chf, 2)}</strong></td>
                  <td className="numeric">{number(row.hours_delta, 2)} h</td>
                </tr>)}</tbody>
              </table>
              {!areaRows.length && !areaPreviewError && <p>No rows have a priced change under this rule.</p>}
            </div>
          )}
          <Field label="Reason for applying this pricing rule">
            <textarea value={areaReason} onChange={(event) => setAreaReason(event.target.value)} required minLength={3} rows={3} />
          </Field>
        </div>
        <div className="modal-footer">
          <Button onClick={() => setAreaDialogOpen(false)}>Cancel</Button>
          <Button disabled={areaPreviewLoading || !!areaPreviewError || areaReason.trim().length < 3} onClick={async () => {
            setAreaSaveError('');
            try {
              await onBulkAreaRule(areaRuleCount, areaReason.trim());
              setAreaDialogOpen(false);
            } catch (error) {
              setAreaSaveError((error as Error).message);
            }
          }}>Confirm area-rate rule</Button>
        </div>
      </Modal>
    </div>
  );
}
function Calculation({
  position: p,
  references,
  mutate,
}: {
  position: Position;
  references: References | null;
  mutate: Mutate;
}) {
  const cost = p.cost;
  const product = references?.catalog.find((c) => c.product_id === p.product_id);
  const rule = references?.productivity.find((r) => r.install_code === p.install_code);
  const costText = (value: string | null | undefined) =>
    p.pricing_basis === 'included_elsewhere' ? 'Covered elsewhere' : money(value, 2);
  const candidate = p.candidates.find((c) => c.product_id === p.product_id) || p.candidates[0];
  return (
    <div className="calculation">
      <div className="calculation-description">
        <Status status={p.status} />
        <h3>{p.description}</h3>
        <span className="text-muted">
          {p.system} · {label(p.category)} {p.origin === 'manual' ? '· Manually added' : ''}
        </span>
      </div>
      <section>
        <h4>
          <span className="step-number">1</span> Quantity & source
        </h4>
        <DetailRow name="Normalized quantity">
          {number(p.quantity, 4)} {p.unit}
        </DetailRow>
        <DetailRow name="Source quantity">
          {p.raw_quantity || 'Not recorded'} {p.raw_unit}
        </DetailRow>
        {Boolean(p.attributes.area_m2 && p.attributes.width_mm && p.attributes.height_mm && p.raw_quantity) && (
          <div className="formula-box">
            PDF geometry: 2 × ({String(p.attributes.width_mm)} + {String(p.attributes.height_mm)}) mm × {p.raw_quantity} mm ÷ 1,000,000
            {p.attributes.schedule_code === 'LT' && ` × ${String(references?.parameters.duct_pricing?.fitting_section_area_factor ?? '1.0')} fitting area factor (project assumption)`}
            {' = '}{String(p.attributes.area_m2)} m²{p.attributes.schedule_code === 'LT'
              ? p.cost?.direct_cost_chf == null ? ' provisional takeoff only; material price remains unresolved.' : ' provisional area-rate price; verify geometry and supplier scope.'
              : ' priced area.'}
          </div>
        )}
        <DetailRow name="Physical PDF page">
          <a
            href={`/api/documents/${p.document_id}/file#page=${p.source_page}`}
            target="_blank"
            rel="noreferrer"
          >
            Page {p.source_page} <ExternalLink size={11} />
          </a>
        </DetailRow>
        {Boolean((Array.isArray(p.attributes.package_source_pages) && p.attributes.package_source_pages.length > 1) || p.attributes.specification_span_text) && (
          <div className="spec-pages-banner">
            <FileText size={15} />
            <span>
              {p.attributes.specification_span_text
                ? String(p.attributes.specification_span_text)
                : `Specification spans pages ${((p.attributes.package_source_pages as number[]) || [])[0]}–${((p.attributes.package_source_pages as number[]) || []).slice(-1)[0]}`}
            </span>
          </div>
        )}
        {Object.keys(p.attributes).length > 0 && (
          <details>
            <summary>Technical attributes & conversions</summary>
            <div className="attributes">
              {Object.entries(p.attributes)
                .filter(([key]) => !key.startsWith('_') && !['pricing_proposals', 'ai_refinement_proposals', 'pricing', 'package_source_pages', 'specification_span_text', 'estimator_area_override'].includes(key) && !key.endsWith('_ids'))
                .map(([k, v]) => (
                  <DetailRow key={k} name={label(k)}>
                    {v == null ? 'Not stated' : Array.isArray(v) ? v.join(', ') : typeof v === 'object'
                      ? Object.entries(v as Record<string, unknown>).map(([key, value]) => `${label(key)}: ${String(value)}`).join(' · ')
                      : String(v)}
                  </DetailRow>
                ))}
            </div>
          </details>
        )}
      </section>
      <section>
        <h4>
          <span className="step-number">2</span> Product pricing reference
        </h4>
        <div className="match-heading">
          <strong>{p.product_id || 'No reference selected'}</strong>
          <Status status={p.match_evidence_band} />
        </div>
        <p>{product?.description || product?.description_de || product?.product_name || ''}</p>
        {p.pricing_basis === 'supplier_reference' && <div className="note compact">Provisional supplier reference from catalog.csv. Obtain a current quote and verify the tender manufacturer, specification and scope before relying on this price.</div>}
        <DetailRow name="Pricing basis">{label(p.pricing_basis)}</DetailRow>
        <DetailRow name="Tender manufacturer">
          {String(p.attributes.manufacturer || p.attributes.manufacturer_name || 'Not stated')}
        </DetailRow>
        <DetailRow name="Reference manufacturer">{product?.manufacturer || 'Unspecified'}</DetailRow>
        <DetailRow name="Technical equivalence">
          <span className={p.technical_equivalence === 'incompatible' ? 'text-red' : ''}>
            {label(p.technical_equivalence)}
          </span>
        </DetailRow>
        {candidate && (
          <div className="constraint-list">
            {candidate.satisfied.map((v) => (
              <div className="text-green" key={v}>
                <Check size={12} />
                {humanEvidence(v)}
              </div>
            ))}
            {candidate.missing.map((v) => (
              <div className="text-amber" key={v}>
                <AlertTriangle size={12} />
                {humanEvidence(v)}
              </div>
            ))}
            {candidate.conflicts.map((v) => (
              <div className="text-red" key={v}>
                <X size={12} />
                {humanEvidence(v)}
              </div>
            ))}
            {candidate.explanation && <p>{humanEvidence(candidate.explanation)}</p>}
          </div>
        )}
        <div className="note compact">
          A pricing reference does not establish approved technical equivalence.
        </div>
        {product && <DetailRow name="Material source">catalog.csv · {product.product_id} · {money(product.net_cost_chf, 2)} per {product.unit}</DetailRow>}
        {cost?.net_unit_cost_chf != null && p.quantity != null && <div className="formula-box">Material: {p.overrides.duct_material_quantity_m2 ? String(p.overrides.duct_material_quantity_m2) : p.quantity} {p.overrides.duct_material_quantity_m2 ? 'm² equivalent' : p.unit} × {money(cost.net_unit_cost_chf, 2)} × (1 + {String(p.overrides.material_waste_pct ?? references?.parameters.allowances?.material_waste_pct ?? '0')}% waste) = {costText(cost.material_cost_chf)}</div>}
        <DetailRow name="Net price / unit">{costText(cost?.net_unit_cost_chf)}</DetailRow>
        <DetailRow name="Waste allowance">{costText(cost?.waste_chf)}</DetailRow>
        <div className="calculation-total">
          <span>Material cost</span>
          <strong>{costText(cost?.material_cost_chf)}</strong>
        </div>
      </section>
      <PositionProposals key={p.id} position={p} mutate={mutate} />
      <section>
        <h4>
          <span className="step-number">3</span> Installation labour
        </h4>
        <DetailRow name="Installation rule">{p.install_code ? label(p.install_code) : 'Missing'}</DetailRow>
        {rule && <DetailRow name="Labour source">productivity.csv · {rule.install_code} · {rule.base_hours_per_unit} h/{rule.unit}</DetailRow>}
        <DetailRow name="Base hours / unit">{cost?.base_hours_per_unit ?? '—'}</DetailRow>
        {Object.entries(cost?.factors || {}).map(([k, v]) => (
          <DetailRow name={label(k)} key={k}>
            {v}
          </DetailRow>
        ))}
        <DetailRow name="Labour role">{cost?.labour_role || 'Unresolved'}</DetailRow>
        <DetailRow name="Hourly rate">{money(cost?.hourly_rate_chf, 2)}</DetailRow>
        <DetailRow name="Installation hours">{number(cost?.adjusted_install_hours)} h</DetailRow>
        <DetailRow name="Unrounded hours used">
          <span className="precision-value">{cost?.unrounded_hours || '—'}</span>
        </DetailRow>
        {cost?.unrounded_hours != null && cost.hourly_rate_chf != null && <div className="formula-box">Labour: {cost.unrounded_hours} h (unrounded) × {money(cost.hourly_rate_chf, 2)}/h = {costText(cost.labour_cost_chf)}. Base: {p.quantity} {p.unit} × {cost.base_hours_per_unit} h/{p.unit}; factors from project assumptions are shown above.</div>}
        {cost?.formula && <div className="formula-box">{cost.formula}</div>}
        <div className="calculation-total">
          <span>Labour cost</span>
          <strong>{costText(cost?.labour_cost_chf)}</strong>
        </div>
      </section>
      <div className="direct-cost-total">
        <span>Direct position cost</span>
        <strong>{costText(cost?.direct_cost_chf)}</strong>
      </div>
      {cost?.direct_cost_chf == null &&
        (cost?.material_cost_chf != null || cost?.labour_cost_chf != null) && (
          <div className="note compact">
            This position has known partial costs. Its complete direct cost remains unresolved; the known
            material and labour components are included in the estimate.
          </div>
        )}
      {p.assumptions.length > 0 && (
        <section>
          <h4>Recorded assumptions</h4>
          {p.assumptions.map((a, i) => (
            <div className="note compact" key={i}>
              {a}
            </div>
          ))}
        </section>
      )}
      {p.warnings.length > 0 && (
        <section>
          <h4>Position issues</h4>
          {p.warnings.map((w) => (
            <div className="warning-note" key={w.id}>
              <AlertTriangle size={14} />
              <div>
                <strong>{w.title}</strong>
                <p>{w.detail}</p>
              </div>
            </div>
          ))}
        </section>
      )}
      {p.included_in && (
        <div className="note">Cost scope belongs to {p.included_in}; excluded here to avoid duplication.</div>
      )}
    </div>
  );
}
