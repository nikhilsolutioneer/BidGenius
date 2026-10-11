import { useState } from 'react';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleHelp,
  FileText,
  Layers,
  Plus,
  ScanLine,
  Settings2,
  ShieldCheck,
  TriangleAlert,
  ExternalLink,
  Pencil,
  X,
} from 'lucide-react';
import { Badge, Button, countOrDash, Empty, Modal, Status } from './components';
import { compareDecimal, date, label, money, number } from './api';
import type { Summary, Adjustment, Issue } from './types';
import { missingCauseLabels } from './coverage';
import { HBar } from './charts/HBar';
import { StackedRangeBar } from './charts/StackedRangeBar';
import { Waterfall } from './charts/Waterfall';
export default function Overview({
  summary,
  onEstimate,
  onScenarios,
  onAnalytics,
  onAssumptions,
  onAdjustment,
  onReviewAdjustment,
  onIssue,
  onRequirement,
  onSource,
}: {
  summary: Summary;
  onEstimate: (cause?: string) => void;
  onScenarios: () => void;
  onAnalytics: () => void;
  onAssumptions: () => void;
  onAdjustment: (a?: Adjustment) => void;
  onReviewAdjustment: (a: Adjustment, state: string) => void;
  onIssue: (issue: Issue) => void;
  onRequirement: (requirement: Summary['requirements'][number]) => void;
  onSource: (page: number) => void;
}) {
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [allowanceOpen, setAllowanceOpen] = useState(false);
  const [requirementsExpanded, setRequirementsExpanded] = useState(false);
  const [group, setGroup] = useState<'system' | 'category'>('system');
  const [issueFilter, setIssueFilter] = useState<'pending' | 'all'>('pending');
  const coverage = summary.coverage;
  const completeness = summary.completeness;
  const buckets = group === 'system' ? summary.by_system : summary.by_category;
  const issues = summary.issues.filter((i) => issueFilter === 'all' || i.review_state !== 'accepted');
  const [showAllIssues, setShowAllIssues] = useState(false);
  const [overviewTab, setOverviewTab] = useState<'review' | 'cost' | 'scope' | 'requirements' | 'risks' | null>(null);
  const detailTiles = [
    { key: 'review', title: 'Review priorities', detail: `${issues.length} issues`, icon: TriangleAlert },
    { key: 'cost', title: 'Cost build-up', detail: 'Costs & offer price', icon: FileText },
    { key: 'scope', title: 'Scope by system', detail: `${summary.by_system.length} groups`, icon: Layers },
    { key: 'requirements', title: 'Requirements', detail: `${summary.requirements.length} requirements`, icon: ShieldCheck },
    { key: 'risks', title: 'Risks', detail: `${summary.adjustments.length} adjustments`, icon: ArrowUpRight },
  ] as const;
  return (
    <div className="page-content overview-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PROJECT INTELLIGENCE</div>
          <h1>Every number. Backed by evidence.</h1>
          <p>Your first estimate, with the context to make it yours.</p>
        </div>
        <div className="inline"><button className="adjust-assumptions-link" onClick={onScenarios}>Adjust assumptions →</button><Button onClick={onAssumptions}><Settings2 size={16} /> Project assumptions</Button></div>
      </div>
      <div className="overview-top">
        <section className="price-card">
          <div className="price-card-top">
            <span>
              INDICATIVE INCLUDED-SCOPE PRICE
              {completeness?.pct_value_priced !== null && completeness?.pct_value_priced !== undefined && (
                <span className="hero-scope-badge"> · {completeness.pct_value_priced}% of estimated value covered</span>
              )}
            </span>
            <Badge tone="dark">DRAFT ESTIMATE</Badge>
          </div>
          <div className="hero-price">
            {money(summary.totals.selling_price_chf)}
          </div>
          {coverage.provisional_priced_positions !== null && coverage.provisional_priced_positions !== undefined && (
            <div className="hero-price-note">Included scope only · {countOrDash(coverage.provisional_priced_positions)} supplier references ({money(coverage.provisional_direct_cost_chf, 2)} direct) await quotes</div>
          )}
          <div className="price-subtitle">
            <span>{money(summary.totals.cost_baseline_chf)} cost baseline</span>
            <span className="dot-separator" /> <span>CHF · before VAT</span>
            <span className="dot-separator" />
            <span>
              {countOrDash(coverage.positions_priced)} priced · {countOrDash(coverage.positions_included_elsewhere)} covered elsewhere · {countOrDash(coverage.positions_unpriced)} unresolved
            </span>
          </div>
          <div className="price-card-bottom">
            <div>
              <ShieldCheck size={18} />
              <span>
                {summary.review_complete ? 'Review complete for included scope' : 'Estimator review required'}
              </span>
            </div>
            <button onClick={() => onEstimate()}>
              Open estimate <ArrowRight size={17} />
            </button>
          </div>
          <div className="price-decoration" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </section>
        <section className="panel full-scope-card">
          <div className="panel-header"><h2>Indicative total project range</h2><Badge tone="amber">Benchmark</Badge></div>
          <div className="scope-price-inputs">
            <span>Included selling price <strong>{money(summary.totals.selling_price_chf)}</strong></span>
            <span>Benchmark exposure <strong>{completeness ? `${money(completeness.allowance_low_chf)}–${money(completeness.allowance_high_chf)}` : '—'}</strong></span>
          </div>
          {completeness && <StackedRangeBar priced={summary.totals.selling_price_chf} low={completeness.allowance_low_chf} median={completeness.allowance_median_chf} high={completeness.allowance_high_chf} />}
          <div className="full-scope-total">⇒ total after commercial assumptions <strong>{summary.likely_total_low && summary.likely_total_high ? `${money(summary.likely_total_low)}–${money(summary.likely_total_high)}` : '—'}</strong></div>
          <small className="scope-method-note">Median marker = included price + unresolved-scope allowance · benchmark only</small>
          {completeness && <button className="coverage-details" onClick={() => setAllowanceOpen(true)}>Inspect benchmark allowances <ArrowRight size={12} /></button>}
        </section>
        <section className="coverage-card panel">
          <div className="panel-header">
            <h2>
              <ScanLine size={18} /> Document coverage
            </h2>
            <Badge
              tone={
                coverage.pages_processed === coverage.total_pages && coverage.total_pages > 0
                  ? 'green'
                  : 'blue'
              }
            >
              {coverage.pages_processed === coverage.total_pages && coverage.total_pages > 0
                ? coverage.partial_pages
                  ? 'Partially extracted'
                  : 'Parsed'
                : 'In progress'}
            </Badge>
          </div>
          <div className="coverage-number">
            {coverage.pages_processed}
            <span> / {coverage.total_pages} pages</span>
          </div>
          <div className="progress-track">
            <div
              style={{
                width: `${coverage.total_pages ? (coverage.pages_processed / coverage.total_pages) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="coverage-footer">
            <span>
              <Layers size={14} /> {coverage.unassigned_blocks} text not yet assigned to a position
            </span>
            <span className={coverage.failed_pages ? 'text-red' : ''}>
              {coverage.failed_pages} failed · {coverage.partial_pages || 0} partial
            </span>
          </div>
          <button className="coverage-details" onClick={() => setCoverageOpen(true)}>
            Inspect page outcomes <ArrowRight size={12} />
          </button>
        </section>
      </div>
      <div className="stat-grid">
        <Stat
          title="Pending reviews"
          value={number(coverage.pending_reviews, 0)}
          icon={<TriangleAlert size={18} />}
          note="Actionable estimator queue"
          tone="amber"
        />
        <Stat
          title="Priced positions"
          value={number(coverage.positions_priced, 0)}
          icon={<Check size={18} />}
          note={coverage.provisional_priced_positions === null || coverage.provisional_priced_positions === undefined
            ? 'Quotes pending'
            : `${countOrDash(coverage.provisional_priced_positions)} use supplier references; quotes pending`}
          tone="green"
        />
        <Stat
          title="Unresolved positions"
          value={number(coverage.positions_unpriced, 0)}
          icon={<CircleHelp size={18} />}
          note="Prioritized by estimated impact"
          tone="amber"
        />
        <Stat
          title="Positions identified"
          value={number(coverage.positions_extracted + coverage.positions_manual, 0)}
          icon={<FileText size={18} />}
          note={`Current estimate · ${coverage.positions_manual} added by estimator`}
        />
      </div>
      {coverage.unresolved_by_cause && (
        <section className="panel coverage-actions">
          <div className="panel-header">
            <div>
              <h2>What needs your decision now</h2>
              <p>
                {coverage.pending_reviews} items are holding back confidence in the estimate. Start with the highest-impact gaps.
              </p>
            </div>
            <Button variant="primary" onClick={() => onEstimate()}>
              <TriangleAlert size={15} /> Review priorities <ArrowRight size={15} />
            </Button>
          </div>
          <div className="panel-body coverage-cause-grid">
            {Object.entries(coverage.unresolved_by_cause).map(([cause, count]) => (
              <Button key={cause} onClick={() => onEstimate(cause)}>
                <span>{missingCauseLabels[cause] || label(cause)}</span>
                <Badge>{count}</Badge>
                <ArrowRight size={14} />
              </Button>
            ))}
          </div>
        </section>
      )}
      <nav className="overview-detail-tiles" aria-label="Overview details">
        {detailTiles.map(({ key, title, detail, icon: Icon }, index) => <button className={index === 0 ? 'featured' : ''} key={key} type="button" aria-haspopup="dialog" onClick={() => setOverviewTab(key)}><Icon size={24} aria-hidden="true" /><strong>{title}</strong><small>{detail}</small></button>)}
        <button className="analytics-shortcut" type="button" onClick={onAnalytics}><ArrowRight size={24} aria-hidden="true" /><strong>Open Analytics</strong><small>Explore cost & scope</small></button>
      </nav>
      <Modal open={overviewTab !== null} onClose={() => setOverviewTab(null)} title={detailTiles.find(tile => tile.key === overviewTab)?.title || 'Estimate details'} description="Inspect the full details of your saved estimate." wide>
      <div className="overview-details-dialog">
      <div className="overview-middle" hidden={overviewTab !== 'cost' && overviewTab !== 'scope'}>
        <section className="panel build-up" hidden={overviewTab !== 'cost'}>
          <div className="panel-header">
            <div>
              <h2>How the estimate adds up</h2>
              <p>Transparent inputs. Deterministic calculations.</p>
            </div>
            <button className="icon-btn" aria-label="Edit cost assumptions" onClick={() => { setOverviewTab(null); onAssumptions(); }}>
              <Settings2 size={17} />
            </button>
          </div>
          <Waterfall steps={summary.build_up} baseline={summary.totals.cost_baseline_chf} offer={summary.totals.selling_price_chf} />
          <div className="panel-total">
            <span>Cost baseline</span>
            <strong>{money(summary.totals.cost_baseline_chf, 2)}</strong>
          </div>
          {summary.likely_total_low && summary.likely_total_median && summary.likely_total_high && (
            <div className="panel-total">
              <span>{summary.likely_total_label || 'Indicative full-scope range (benchmark-based, not a bid)'}</span>
              <strong>{money(summary.likely_total_low, 2)} – {money(summary.likely_total_median, 2)} – {money(summary.likely_total_high, 2)}</strong>
            </div>
          )}
        </section>
        <section className="panel breakdown-panel" hidden={overviewTab !== 'scope'}>
          <div className="panel-header">
            <div>
              <h2>Scope breakdown</h2>
              <p>One estimate, two perspectives.</p>
            </div>
            <div className="segmented">
              <button className={group === 'system' ? 'active' : ''} onClick={() => setGroup('system')}>
                System
              </button>
              <button className={group === 'category' ? 'active' : ''} onClick={() => setGroup('category')}>
                Category
              </button>
            </div>
          </div>
          <div className="breakdown-list">
            {buckets.map((bucket, i) => (
              <div className="breakdown-item" key={bucket.key}>
                <div className={`system-icon color-${i % 5}`}>
                  <Layers size={17} />
                </div>
                <div className="breakdown-label">
                  <strong>{bucket.label || label(bucket.key)}</strong>
                  <small>
                    {bucket.positions} positions {bucket.unpriced > 0 && `· ${bucket.unpriced} unpriced`}
                  </small>
                </div>
                <div className="breakdown-value">
                  <strong>{compareDecimal(bucket.amount_chf, '0') === 0 ? 'No priced cost' : money(bucket.amount_chf, 2)}</strong>
                  {compareDecimal(bucket.amount_chf, '0') !== 0 && <small>
                    {money(bucket.material_cost_chf)} material · {money(bucket.labour_cost_chf)} labour
                  </small>}
                </div>
              </div>
            ))}
          </div>
          <div className="panel-total">
            <span>Reconciles to cost baseline</span>
            <strong>{money(summary.totals.cost_baseline_chf, 2)}</strong>
          </div>
        </section>
      </div>
      <section className="panel review-panel overview-tab-panel" hidden={overviewTab !== 'review'}>
        <div className="panel-header">
          <div>
            <h2>
              <TriangleAlert size={18} /> Review priorities{' '}
              <span className="count-pill">{issues.length}</span>
            </h2>
            <p>Resolve uncertain scope before making a commercial commitment.</p>
          </div>
          <div className="segmented">
            <button
              className={issueFilter === 'pending' ? 'active' : ''}
              onClick={() => setIssueFilter('pending')}
            >
              Pending
            </button>
            <button className={issueFilter === 'all' ? 'active' : ''} onClick={() => setIssueFilter('all')}>
              All
            </button>
          </div>
        </div>
        {issues.length === 0 ? (
          <Empty icon={<ShieldCheck size={28} />} title="No open review issues">
            Position approvals and unpriced scope remain visible in the estimate.
          </Empty>
        ) : (
          <div className="issue-list">
            {summary.review_cause_stakes && summary.review_cause_stakes.length > 0 && (
              <HBar items={summary.review_cause_stakes} onCause={(cause) => { setOverviewTab(null); onEstimate(cause); }} />
            )}
            {(summary.issue_groups?.length ? summary.issue_groups : issues.map((issue) => ({ group_key: issue.title, kind: issue.kind, detail: issue.detail, count: 1, pages: [], issue_ids: [issue.id], source_span_ids: issue.source_span_ids }))).slice(0, showAllIssues ? undefined : 5).map((issue) => {
              const sourceIssue = issues.find((candidate) => candidate.id === issue.issue_ids[0]);
              if (!sourceIssue) return null;
              return <button className="issue-item" key={issue.group_key} onClick={() => { setOverviewTab(null); onIssue(sourceIssue); }}>
                <span className={`issue-symbol ${sourceIssue.severity}`}>
                  <TriangleAlert size={17} />
                </span>
                <div>
                  <div className="issue-title">
                    {issue.group_key}
                    <Badge tone="blue">×{issue.count} pages</Badge>
                    <Badge tone={sourceIssue.severity === 'blocker' ? 'red' : 'amber'}>
                      {label(sourceIssue.severity)}
                    </Badge>
                    {sourceIssue.review_state === 'accepted' && <Badge tone="green">Reviewed</Badge>}
                  </div>
                  <p>{issue.detail}</p><div className="page-chips">{issue.pages.map((page) => <span key={page}>p. {page || '—'}</span>)}</div>
                  <small>
                    {issue.source_span_ids.length} evidence references · {label(issue.kind)}
                  </small>
                </div>
                <ArrowRight size={17} />
              </button>;
            })}
          </div>
        )}
        {issues.length > 5 && (
          <button className="show-more" onClick={() => setShowAllIssues((v) => !v)}>
            {showAllIssues ? 'Show fewer issues' : `View all ${issues.length} issues`}{' '}
            <ArrowRight size={14} />
          </button>
        )}
      </section>
      <section className="panel overview-tab-panel" hidden={overviewTab !== 'risks'}>
        <div className="panel-header">
          <div>
            <h2>Risk & opportunity register</h2>
            <p>Commercial judgment, explicitly recorded. Only approved entries affect the estimate.</p>
          </div>
          <Button onClick={() => { setOverviewTab(null); onAdjustment(); }}>
            <Plus size={16} /> Add adjustment
          </Button>
        </div>
        <div>
        {summary.adjustments.length === 0 ? (
          <div className="register-empty">
            <div className="register-icon">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h3>No additional commercial adjustments</h3>
              <p>
                Existing allowances are already included. Add a supported risk or opportunity when the
                evidence calls for it.
              </p>
            </div>
            <Badge>CHF 0 additional</Badge>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table adjustment-table">
              <thead>
                <tr>
                  <th>Adjustment</th>
                  <th>Amount</th>
                  <th>Scope / basis</th>
                  <th>Approval</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {summary.adjustments.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="inline">
                        {a.kind === 'risk' ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                        <strong>{a.title}</strong>
                      </div>
                      <small>{label(a.kind)}</small>
                    </td>
                    <td className="numeric">
                      {a.kind === 'risk' ? '+' : '−'}
                      {money(a.amount_chf, 2)}
                    </td>
                    <td>
                      <div>{label(a.scope)}</div>
                      <small>{a.basis}</small>
                    </td>
                    <td>
                      <Status status={a.review_state} />
                    </td>
                    <td>
                      <div className="inline">
                        <button
                          className="icon-btn"
                          title="Edit adjustment"
                          aria-label={`Edit ${a.title}`}
                          onClick={() => { setOverviewTab(null); onAdjustment(a); }}
                        >
                          <Pencil size={14} />
                        </button>
                        {a.review_state !== 'accepted' && (
                          <button
                            className="icon-btn text-green"
                            aria-label={`Approve ${a.title}`}
                            title="Approve adjustment"
                            onClick={() => { setOverviewTab(null); onReviewAdjustment(a, 'accepted'); }}
                          >
                            <Check size={16} />
                          </button>
                        )}
                        {a.review_state !== 'rejected' && (
                          <button
                            className="icon-btn"
                            title="Reject adjustment"
                            aria-label={`Reject ${a.title}`}
                            onClick={() => { setOverviewTab(null); onReviewAdjustment(a, 'rejected'); }}
                          >
                            <X size={15} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="register-footer">
          <span>
            Approved risks <strong>{compareDecimal(summary.totals.risk_adjustments_chf || '0', '0') === 0 ? 'None' : money(summary.totals.risk_adjustments_chf, 2)}</strong>
          </span>
          <span>
            Approved opportunities{' '}
            <strong>{compareDecimal(summary.totals.opportunity_adjustments_chf || '0', '0') === 0 ? 'None' : money(summary.totals.opportunity_adjustments_chf, 2)}</strong>
          </span>
          <span>
            Pending net preview{' '}
            <strong>{compareDecimal(summary.totals.pending_adjustment_delta_chf || '0', '0') === 0 ? 'None' : money(summary.totals.pending_adjustment_delta_chf, 2)}</strong>
          </span>
        </div>
        </div>
      </section>
      {summary.requirements.length > 0 && (
        <section className="panel requirements overview-tab-panel" hidden={overviewTab !== 'requirements'}>
          <div>
          <div className="panel-header">
            <div>
              <h2>Tender requirements</h2>
              <p>Obligations and restrictions preserved from the source.</p>
            </div>
            <Badge>{summary.requirements.length} identified</Badge>
          </div>
          {(requirementsExpanded ? summary.requirements : summary.requirements.slice(0, 8)).map((r) => (
            <div key={r.id} className="requirement-row">
              <FileText size={16} />
              <div>
                <strong>
                  {r.title} {r.review_state === 'accepted' && <Badge tone="green">Reviewed</Badge>}
                </strong>
                <p>{r.description}</p>
                {r.review_state !== 'accepted' && (
                  <button className="text-btn" onClick={() => { setOverviewTab(null); onRequirement(r); }}>
                    <Check size={12} /> Mark reviewed
                  </button>
                )}
              </div>
              <a
                className="text-btn"
                href={`/api/documents/${summary.document.id}/file#page=${r.source_page}`}
                target="_blank"
                rel="noreferrer"
              >
                p. {r.source_page}
                <ExternalLink size={13} />
              </a>
            </div>
          ))}
          {summary.requirements.length > 8 && (
            <button className="show-more" onClick={() => setRequirementsExpanded((v) => !v)}>
              {requirementsExpanded
                ? 'Show fewer requirements'
                : `View all ${summary.requirements.length} requirements`}{' '}
              <ArrowRight size={14} />
            </button>
          )}
          </div>
        </section>
      )}
      {overviewTab === 'requirements' && summary.requirements.length === 0 && <Empty title="No tender requirements identified" />}
      </div>
      </Modal>
      <div className="page-footnote">
        <ShieldCheck size={13} /> Local workspace · Revision {summary.revision} ·{' '}
        {summary.latest_run?.completed_at
          ? `Processed ${date(summary.latest_run.completed_at)}`
          : 'Reviewable draft'}{' '}
        · Source documents remain unchanged
      </div>
      <Modal
        open={coverageOpen}
        onClose={() => setCoverageOpen(false)}
        title="Page processing outcomes"
        description="Processed pages may contain unresolved blocks. This is not a completeness guarantee."
        wide
      >
        <div className="modal-body">
          {(summary.unresolved_sources || []).length > 0 && (
            <section className="unresolved-source-list">
              <h3>Text not yet assigned to a position</h3>
              <p className="text-muted">
                Inspect these blocks and recover any missing position from the source.
              </p>
              {summary.unresolved_sources!.map((s) => (
                <div className="unresolved-source" key={s.id}>
                  <p>{s.text}</p>
                  <Button
                    onClick={() => {
                      setCoverageOpen(false);
                      onSource(s.page);
                    }}
                  >
                    <FileText size={13} /> Review page {s.page}
                    <ArrowRight size={13} />
                  </Button>
                </div>
              ))}
            </section>
          )}
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Page</th>
                  <th>System</th>
                  <th>Parsing</th>
                  <th>Extraction</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {(summary.page_outcomes || []).map((p) => (
                  <tr key={p.page}>
                    <td>
                      <a
                        className="text-btn"
                        href={`/api/documents/${summary.document.id}/file#page=${p.page}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Page {p.page}
                        <ExternalLink size={12} />
                      </a>
                    </td>
                    <td>{p.system}</td>
                    <td>{label(p.status || 'unknown')}</td>
                    <td>{label(p.extraction_status || 'unresolved')}</td>
                    <td>{p.warnings.join('; ') || '?'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="modal-footer">
          <Button onClick={() => setCoverageOpen(false)}>Close</Button>
        </div>
      </Modal>

      {completeness && (
        <Modal
          open={allowanceOpen}
          title="Unpriced Scope Benchmark Allowance"
          description="Advisory estimate for unresolved scope. It does not add or change positions and is not included in the offer."
          wide
          onClose={() => setAllowanceOpen(false)}
        >
          <div className="modal-body benchmark-dialog-body">
            <div className="note" style={{ marginBottom: '16px' }}>
              <strong>Benchmark exposure: {money(completeness.allowance_low_chf)} – {money(completeness.allowance_high_chf)} (Median {money(completeness.allowance_median_chf)})</strong>
              <p style={{ marginTop: '4px', fontSize: '12px' }}>
                {completeness.positions_with_allowance} of {completeness.positions_unpriced} unpriced positions have a known quantity and matching installation group. Their benchmark uses prices in the same group and unit; known partial costs are deducted.
                {` ${completeness.positions_no_basis} positions have no benchmark basis and are excluded from the value-share figure.`}
                This allowance is <strong>never automatically added</strong> to the baseline. You can adopt it as a risk adjustment via the Risk &amp; Opportunity register.
              </p>
            </div>

            <div className="benchmark-stats">
              <div style={{ background: 'var(--bg)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                <span style={{ fontSize: '12px', color: 'var(--muted)', display: 'block' }}>Unpriced positions with benchmark basis</span>
                <strong style={{ fontSize: '16px', color: 'var(--text)' }}>{completeness.positions_with_allowance}</strong>
              </div>
              <div style={{ background: 'var(--bg)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                <span style={{ fontSize: '12px', color: 'var(--muted)', display: 'block' }}>Unpriced positions without basis</span>
                <strong style={{ fontSize: '16px', color: 'var(--danger)' }}>{completeness.positions_no_basis}</strong>
              </div>
              <div style={{ background: 'var(--bg)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                <span style={{ fontSize: '12px', color: 'var(--muted)', display: 'block' }}>Known direct cost, including partials and services</span>
                <strong style={{ fontSize: '16px', color: 'var(--text)' }}>{money(completeness.priced_direct_cost_chf)}</strong>
              </div>
              <div style={{ background: 'var(--bg)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                <span style={{ fontSize: '12px', color: 'var(--muted)', display: 'block' }}>Known cost ÷ (known cost + benchmark gap)</span>
                <strong style={{ fontSize: '16px', color: 'var(--success)' }}>{completeness.pct_value_priced}%</strong>
              </div>
            </div>

            <h3 style={{ fontSize: '14px', marginBottom: '10px' }}>Benchmark Unit Rates by Group</h3>
            <div className="table-scroll" style={{ maxHeight: '240px', marginBottom: '20px' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Install Code</th>
                    <th>Unit</th>
                    <th>Priced Sample</th>
                    <th>P25 Rate</th>
                    <th>Median Rate</th>
                    <th>P75 Rate</th>
                    <th>Traceable Reference Positions</th>
                  </tr>
                </thead>
                <tbody>
                  {completeness.benchmark_groups.map((g) => (
                    <tr key={`${g.install_code}-${g.unit}`}>
                      <td><code>{g.install_code}</code></td>
                      <td>{g.unit}</td>
                      <td>{g.sample_size} positions</td>
                      <td>{money(g.p25_unit_rate_chf)}</td>
                      <td><strong>{money(g.median_unit_rate_chf)}</strong></td>
                      <td>{money(g.p75_unit_rate_chf)}</td>
                      <td className="text-muted" title={g.references.join(', ')}>
                        {g.references.slice(0, 3).join(', ')}{g.references.length > 3 ? ` +${g.references.length - 3} more` : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ fontSize: '14px', marginBottom: '10px' }}>Top Unpriced Positions &amp; Benchmark Allowances</h3>
            <div className="table-scroll" style={{ maxHeight: '280px' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Description</th>
                    <th>Quantity</th>
                    <th>Unit Rate</th>
                    <th>Median Allowance</th>
                    <th>Basis Status</th>
                  </tr>
                </thead>
                <tbody>
                  {completeness.itemized_allowances.slice(0, 50).map((item) => (
                    <tr key={item.position_id}>
                      <td><strong>{item.reference}</strong></td>
                      <td title={item.description}>
                        {item.description}
                      </td>
                      <td>{item.quantity ? `${item.quantity} ${item.unit}` : <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                      <td>{item.median_unit_rate_chf ? `${money(item.median_unit_rate_chf)}/${item.unit}` : '—'}</td>
                      <td>{item.allowance_median_chf ? <strong>{money(item.allowance_median_chf)}</strong> : '—'}</td>
                      <td>
                        {item.basis_status === 'benchmark_matched' ? (
                          <Badge tone="green">Matched ({item.benchmark_sample_size} refs)</Badge>
                        ) : (
                          <Badge tone="amber">{item.no_basis_reason === 'missing_quantity' ? 'Missing qty' : 'No group basis'}</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
              Want to include this scope in the tender offer? Adopt as a risk adjustment.
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button
                variant="primary"
                disabled={!completeness.positions_with_allowance || Number(completeness.allowance_median_chf) <= 0}
                onClick={() => {
                  setAllowanceOpen(false);
                  onAdjustment({
                    id: '',
                    kind: 'risk',
                    title: `Unpriced scope benchmark allowance (${completeness.positions_with_allowance} positions)`,
                    amount_chf: completeness.allowance_median_chf,
                    scope: 'project_level',
                    basis: `Median benchmark unit costs across ${completeness.benchmark_groups.length} installation groups (${completeness.positions_with_allowance} unpriced items). Range CHF ${completeness.allowance_low_chf} to CHF ${completeness.allowance_high_chf}.`,
                    source_span_ids: [],
                    review_state: 'pending',
                    overlap_resolution: 'incremental unpriced tender scope benchmark allowance',
                    created_at: '',
                    updated_at: '',
                  });
                }}
              >
                Adopt median as risk adjustment ({money(completeness.allowance_median_chf)})
              </Button>
              <Button onClick={() => setAllowanceOpen(false)}>Close</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
function Stat({
  title,
  value,
  note,
  icon,
  tone = 'blue',
}: {
  title: string;
  value: string;
  note: string;
  icon: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-title">
        <span>{title}</span>
        <span className={`stat-icon ${tone}`}>{icon}</span>
      </div>
      <div className="stat-value">{value}</div>
      <small>{note}</small>
    </div>
  );
}
