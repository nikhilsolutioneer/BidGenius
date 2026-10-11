import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  Activity,
  BarChart3,
  ArrowRight,
  Building2,
  Check,
  ChevronDown,
  FileCheck2,
  FileInput,
  FileText,
  FolderOpen,
  Gauge,
  GitBranch,
  HardDrive,
  Import,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Square,
  Table2,
  TriangleAlert,
  Upload,
  X,
} from 'lucide-react';
import { ApiError, api, date, label, money, patch, post } from './api';
import { Badge, Button, ErrorBox, Modal, Spinner, Status } from './components';
import { AdjustmentDialog, AssumptionsDialog, ManualDialog, PositionDialog, ReasonDialog } from './Dialogs';
import type { Mutate } from './Dialogs';
import Overview from './Overview';
import Analytics from './Analytics';
import Management from './Management';
import Workspace from './Workspace';
import type { Bid } from './Management';
import Estimate from './Estimate';
import Assistant from './Assistant';
import { useLanguage, translate } from './i18n';
import { LanguageSelector } from './i18n/LanguageSelector';
import { ExportPage, ScenarioPage } from './ScenarioExport';
import type {
  Adjustment,
  Health,
  History,
  Issue,
  Position,
  Project,
  References,
  Run,
  SourceSpan,
  Summary,
} from './types';
type Page = 'workspace' | 'overview' | 'estimate' | 'analytics' | 'scenarios' | 'export' | 'management';
type BidStatus = NonNullable<Project['bid_status']>;
type PinnedDemo = { project_id: string; prepared_at: string | null; project_name: string };
type ReasonTask = {
  title: string;
  description: string;
  delta?: string;
  submit: (reason: string) => Promise<unknown>;
};
const activeRun = (r: Run | null | undefined) => !!r && ['queued', 'running'].includes(r.status);
const hybridRun = (run: Run) => run.extraction_mode === 'local_then_ai';
const supportsSelectiveAI = (health: Health | null) => !!health?.ai_configured && !!health.processing_modes?.includes('local_then_ai');
const usageCount = (run: Run, key: string) => Number(run.usage[key]) || 0;
const extractionModeLabels: Record<string, string> = {
  local: 'Local extraction',
  local_then_ai: 'Local first, then AI for gaps',
  openai: 'AI extraction',
  mixed: 'Local and AI extraction',
};
const extractionModeLabel = (run: Run) => extractionModeLabels[run.extraction_mode] || label(run.extraction_mode);
const runStageLabel = (run: Run) => {
  if (hybridRun(run)) {
    if (run.stage.startsWith('local extraction')) return `Step 1 of 2 · ${label(run.stage)}`;
    if (run.stage.toLowerCase().startsWith('ai review')) return `Step 2 of 2 · ${run.stage}`;
    if (run.stage === 'selecting unresolved items for AI') return 'Step 2 of 2 · Selecting unresolved items for AI';
  }
  return label(run.stage);
};
const reviewingGaps = (run: Run) => hybridRun(run) && (run.ai_batches_total > 0 || run.stage.toLowerCase().startsWith('ai review'));
const runProgress = (run: Run) => reviewingGaps(run)
  ? run.ai_batches_total ? (run.ai_batches_done / run.ai_batches_total) * 100 : 0
  : run.total_pages ? (run.pages_processed / run.total_pages) * 100 : 0;
const usageLabels: Record<string, string> = {
  ai_review_positions: 'Unresolved positions selected for AI',
  ai_review_source_blocks: 'Source blocks selected for AI',
  ai_positions_added: 'Positions added by AI',
  ai_positions_refined: 'AI refinements for review',
  ai_skipped_batches: 'AI review batches skipped',
  successful_ai_batches: 'Successful AI review batches',
  failed_ai_batches: 'Failed AI review batches',
  cached_ai_batches: 'AI review batches reused from cache',
};
const statusLabels: Record<BidStatus, string> = {
  draft: 'Draft',
  in_review: 'Ready for review',
  approved: 'Approved',
  submitted: 'Submitted',
};
const estimatorStatuses: BidStatus[] = ['draft', 'in_review'];
const managementStatuses: BidStatus[] = ['draft', 'in_review', 'approved', 'submitted'];
export default function App() {
  useLanguage();
  const [health, setHealth] = useState<Health | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [pinnedDemo, setPinnedDemo] = useState<PinnedDemo | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [references, setReferences] = useState<References | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [page, setPage] = useState<Page>(() => localStorage.getItem('bidgenius_role') === 'Management' ? 'management' : 'workspace');
  const [initialCause, setInitialCause] = useState('all');
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sourcePage, setSourcePage] = useState<number | null>(null);
  const [positionEdit, setPositionEdit] = useState<Position | null>(null);
  const [manualSpans, setManualSpans] = useState<SourceSpan[] | null>(null);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [adjustmentEdit, setAdjustmentEdit] = useState<Adjustment | undefined | null>(null);
  const [reasonTask, setReasonTask] = useState<ReasonTask | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [processingOpen, setProcessingOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [issueOpen, setIssueOpen] = useState<Issue | null>(null);
  const [useAI, setUseAI] = useState(false);
  const [role, setRole] = useState(localStorage.getItem('bidgenius_role') || 'Estimator');
  const [actor, setActor] = useState(localStorage.getItem('bidgenius_actor') || 'Local estimator');
  const [loggedIn, setLoggedIn] = useState(localStorage.getItem('bidgenius_session') === 'active');
  const [managementBids, setManagementBids] = useState<Bid[] | null>(null);
  const [managementError, setManagementError] = useState('');
  const [managementLoading, setManagementLoading] = useState(false);
  const [managementRetry, setManagementRetry] = useState(0);
  useEffect(() => {
    if (!loggedIn || role !== 'Management') return;
    let current = true;
    setManagementError('');
    setManagementLoading(true);
    void api<Bid[]>('/admin/bids').then(data => {
      if (current) setManagementBids(data);
    }).catch((e: Error) => {
      if (current) setManagementError(e.message);
    }).finally(() => {
      if (current) setManagementLoading(false);
    });
    return () => { current = false; };
  }, [loggedIn, role, projects, project?.revision, managementRetry]);
  const [profileOpen, setProfileOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceEstimator, setWorkspaceEstimator] = useState('');
  const [loginRole, setLoginRole] = useState(localStorage.getItem('bidgenius_role') || 'Estimator');
  const [loginName, setLoginName] = useState(localStorage.getItem('bidgenius_actor') || 'Local estimator');
  const [runOptionsOpen, setRunOptionsOpen] = useState(false);
  const projectRef = useRef<Project | null>(null);
  const mounted = useRef(true);
  const refresh = useCallback(async (id: string) => {
    const [p, s, pos, refs] = await Promise.all([
      api<Project>(`/projects/${id}`),
      api<Summary>(`/projects/${id}/summary`),
      api<{ items: Position[] }>(`/projects/${id}/positions`),
      api<References>(`/projects/${id}/references`),
    ]);
    if (!mounted.current) return;
    setProject(p);
    projectRef.current = p;
    setSummary(s);
    setPositions(pos.items);
    setReferences(refs);
    setRun(p.latest_run || s.latest_run);
    localStorage.setItem('tenderproof_project', id);
  }, []);
  const loadProject = useCallback(
    async (id: string) => {
      setBusy(true);
      setError('');
      setSelectedId(null);
      setSourcePage(null);
      setProjectsOpen(false);
      try {
        await refresh(id);
        setPage('overview');
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );
  const changeBidStatus = async (nextStatus: BidStatus) => {
    if (!project || statusBusy) return;
    const currentStatus = project.bid_status || 'draft';
    if (nextStatus === currentStatus) return;
    const reason = window.prompt(`Why move this bid from ${statusLabels[currentStatus]} to ${statusLabels[nextStatus]}?`);
    if (!reason?.trim()) return;
    setStatusBusy(true);
    setError('');
    try {
      await patch(`/projects/${project.id}/meta`, { bid_status: nextStatus, reason: reason.trim() });
      await refresh(project.id);
      setToast(`Status updated to ${statusLabels[nextStatus]}.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStatusBusy(false);
    }
  };
  useEffect(() => {
    mounted.current = true;
    const init = async () => {
      try {
        const [h, ps, pin] = await Promise.all([
          api<Health>('/health'),
          api<Project[]>('/projects'),
          api<PinnedDemo | null>('/pinned-demo'),
        ]);
        if (!mounted.current) return;
        setHealth(h);
        setProjects(ps);
        setPinnedDemo(pin && ps.some((p) => p.id === pin.project_id) ? pin : null);
        const stored = localStorage.getItem('tenderproof_project');
        const id = ps.find((p) => p.id === pin?.project_id)?.id || ps.find((p) => p.id === stored)?.id || ps[0]?.id;
        if (id) await refresh(id);
      } catch (e) {
        if (mounted.current) setError(`Could not connect to the local server. ${(e as Error).message}`);
      } finally {
        if (mounted.current) setBooting(false);
      }
    };
    void init();
    return () => {
      mounted.current = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!run || !activeRun(run)) return;
    let inFlight = false;
    const timer = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const next = await api<Run>(`/runs/${run.id}`);
        setRun(next);
        if (!activeRun(next)) {
          await refresh(next.project_id);
          setToast(
            next.status === 'awaiting_review'
              ? 'Processing finished. Your estimate is ready for review.'
              : `Processing ${label(next.status).toLowerCase()}.`,
          );
          setProjects(await api<Project[]>('/projects'));
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        inFlight = false;
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [run?.id, run?.status, refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 6500);
    return () => clearTimeout(timer);
  }, [toast]);
  const mutate: Mutate = async (path, body, method = 'PATCH') => {
    const current = projectRef.current;
    if (!current) throw new Error('No project selected.');
    try {
      const result = await (method === 'POST' ? post : patch)<{
        price_delta_chf?: string;
        cost_delta_chf?: string;
        revision?: number;
      }>(path, { expected_revision: current.revision, ...body });
      await refresh(current.id);
      setToast(
        `Revision ${result.revision ?? projectRef.current?.revision} saved${result.cost_delta_chf !== undefined ? ` / Cost change ${money(result.cost_delta_chf, 2)}` : ''}${result.price_delta_chf !== undefined ? ` / Offer change ${money(result.price_delta_chf, 2)}` : ''}`,
      );
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await refresh(current.id);
      throw e;
    }
  };
  const openDemo = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await post<{ project_id: string; run_id: string }>('/projects/demo', { use_ai: useAI && supportsSelectiveAI(health) });
      await refresh(result.project_id);
      setProjects(await api<Project[]>('/projects'));
      setProcessingOpen(true);
      setPage('overview');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const select = (id: string | null) => {
    setSelectedId(id);
    setSourcePage(null);
  };
  const onUndo = (h: History) =>
    setReasonTask({
      title: 'Reverse this decision',
      description: `Create a reversing revision for: ${h.reason}`,
      delta: h.price_delta_chf,
      submit: (reason) => mutate(`/projects/${project!.id}/undo/${h.id}`, { reason }, 'POST'),
    });
  const onAccept = (p: Position) =>
    setReasonTask({
      title: 'Accept position review',
      description:
        'Confirm the reviewed quantity, pricing basis, and assumptions. Technical equivalence remains a separate decision.',
      submit: (reason) => mutate(`/positions/${p.id}`, { reason, changes: { review_state: 'accepted' } }),
    });
  const onBulkAreaRule = (_count: number, reason: string) =>
    mutate(`/projects/${project!.id}/duct-area-rule`, { reason }, 'POST');
  const onReviewAdjustment = (a: Adjustment, state: string) =>
    setReasonTask({
      title: state === 'accepted' ? 'Approve commercial adjustment' : 'Reject commercial adjustment',
      description: `${a.title}. ${state === 'accepted' ? 'The approved amount will enter the cost build-up.' : 'This amount will be excluded from the estimate.'}`,
      delta: a.amount_chf,
      submit: (reason) => mutate(`/adjustments/${a.id}`, { reason, changes: { review_state: state } }),
    });
  const onResume = (action: 'continue' | 'complete_review') => {
    if (!run || !project) return;
    setReasonTask({
      title: action === 'continue' ? 'Resume saved processing' : 'Complete estimator review',
      description:
        action === 'continue'
          ? 'Continue from the persisted checkpoint. Completed batches will be retained.'
          : 'The backend checks unresolved blockers before completing review.',
      submit: (reason) => mutate(`/runs/${run.id}/resume`, { reason, action }, 'POST'),
    });
  };
  const onStartRun = async () => {
    if (!project) return;
    setBusy(true);
    setError('');
    try {
      await post(`/projects/${project.id}/runs`, { use_ai: useAI && supportsSelectiveAI(health) });
      await refresh(project.id);
      setRunOptionsOpen(false);
      setProcessingOpen(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const navItems: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'estimate', label: 'Estimate', icon: Table2 },
    { id: 'analytics', label: 'Analytics', icon: Activity },
    { id: 'scenarios', label: 'Scenarios', icon: GitBranch },
    { id: 'export', label: 'Export', icon: FileCheck2 },
  ];
  const duplicateVariant = async (sourceId?: string) => {
    const source = projects.find(p => p.id === (sourceId || project?.id));
    if (!source) return;
    const name = window.prompt(translate('Variant name'), `${source.name} — ${translate('variant')}`);
    const estimator = window.prompt(translate('Estimator name'), actor);
    if (!name || !estimator) return;
    try { const created = await post<Project>(`/projects/${source.id}/duplicate`, { name, estimator }); setProjects(await api<Project[]>('/projects')); setProjectsOpen(false); await loadProject(created.id); } catch (e) { setError((e as Error).message); }
  };
  const estimatorNames = [...new Set(projects.map(p => p.estimator || 'Local estimator'))].sort();
  const selectWorkspace = async (estimator: string) => {
    setWorkspaceEstimator(estimator);
    setWorkspaceOpen(false);
    setPage('management');
    const first = estimator ? projects.find(p => (p.estimator || 'Local estimator') === estimator) : undefined;
    if (first) await loadProject(first.id);
  };
  if (role === 'Management') navItems.push({ id: 'management', label: 'Management', icon: BarChart3 });
  else navItems.unshift({ id: 'workspace', label: 'My workspace', icon: FolderOpen });
  if (!loggedIn) {
    return (
      <main className="login-screen">
        <div className="login-language"><LanguageSelector /></div>
        <div className="login-shell">
          <section className="login-hero">
            <img src="/brand/equans-switzerland.svg" alt="Equans Switzerland" className="login-equans-logo" />
            <div className="login-brand"><span translate="no">bid</span><b translate="no">AI</b></div>
            <p className="login-slogan">Price Smarter.<br />Bid Better.<br />Win More.</p>
            <p className="login-powered">— Powered by AI.</p>
            <div className="login-orbit"><span /><span /><span /></div>
            <small>Intelligent tendering for the built environment</small>
          </section>
          <section className="login-card">
            <span className="eyebrow">WELCOME BACK</span>
            <h1>Enter your workspace</h1>
            <p>Choose your access level to continue.</p>
            <div className="login-role-tabs" role="tablist"><button className={loginRole === 'Estimator' ? 'active' : ''} onClick={() => setLoginRole('Estimator')}>Estimator</button><button className={loginRole === 'Management' ? 'active' : ''} onClick={() => setLoginRole('Management')}>Management</button></div>
            <label>{loginRole === 'Management' ? 'Admin name' : 'Estimator name'}<input autoFocus value={loginName} onChange={e => setLoginName(e.target.value)} placeholder={loginRole === 'Management' ? 'Enter admin name' : 'Enter your name'} /></label>
            <button className="login-submit" onClick={() => { const name = loginName.trim() || (loginRole === 'Management' ? 'Admin user' : 'Local estimator'); setRole(loginRole); setActor(name); setWorkspaceEstimator(''); setWorkspaceOpen(false); setPage(loginRole === 'Management' ? 'management' : 'workspace'); localStorage.setItem('bidgenius_role', loginRole); localStorage.setItem('bidgenius_actor', name); localStorage.setItem('bidgenius_session', 'active'); setLoggedIn(true); }}>Open workspace <ArrowRight size={16} /></button>
            <small>Demo access · production uses Entra ID</small>
          </section>
        </div>
      </main>
    );
  }
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage(role === 'Management' ? 'management' : 'workspace');
          }}
          aria-label="BidGenius AI overview"
        >
          <span className="brand-monogram" aria-hidden="true">BG</span>
          <span className="brand-identity">
            <img className="brand-equans" src="/brand/equans-switzerland.svg" alt="Equans Switzerland" width="389" height="119" />
            <span className="brand-product">
              <span className="brand-name" translate="no">BidGenius</span><span className="brand-ai" translate="no">AI</span>
            </span>
          </span>
        </a>
        <button className={`sidebar-workspace ${role === 'Management' ? 'workspace-switcher' : ''}`} onClick={() => role === 'Management' ? setWorkspaceOpen(v => !v) : setPage('workspace')} aria-expanded={role === 'Management' ? workspaceOpen : undefined}>
          <span className="workspace-avatar">E</span>
          <div>
            <strong>{role === 'Management' && workspaceEstimator ? workspaceEstimator : role === 'Management' ? 'Equans organization' : 'Built for Equans estimators'}</strong>
            <span>
              <span className="live-dot" /> Local environment
            </span>
          </div>
          <HardDrive size={16} />
          {role === 'Management' && workspaceOpen && <div className="workspace-menu" onClick={e => e.stopPropagation()}><button className={!workspaceEstimator ? 'selected' : ''} onClick={() => void selectWorkspace('')}><span>All estimators</span><small>{projects.length} bids</small></button>{estimatorNames.map(name => <button className={workspaceEstimator === name ? 'selected' : ''} key={name} onClick={() => void selectWorkspace(name)}><span>{name}</span><small>{projects.filter(p => (p.estimator || 'Local estimator') === name).length} bids</small></button>)}</div>}
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navItems.map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              className={`nav-item ${page === item.id ? 'active' : ''}`}
              disabled={!project && item.id !== 'overview' && item.id !== 'management' && item.id !== 'workspace'}
              onClick={() => setPage(item.id)}
              aria-current={page === item.id ? 'page' : undefined}
            >
              <item.icon size={19} />
              <span>{item.label}</span>
              {item.id === 'estimate' && summary && summary.coverage.pending_reviews > 0 && (
                <span className="nav-count">{summary.coverage.pending_reviews}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <div className="nav-label">PROJECT</div>
        <button className="nav-item" aria-label="Import tender" onClick={() => setImportOpen(true)}>
          <Import size={18} />
          <span>Import tender</span>
        </button>
        <button className="nav-item" aria-label="Saved projects" onClick={() => setProjectsOpen(true)}>
          <FolderOpen size={18} />
          <span>Saved projects</span>
          {projects.length > 0 && <span className="nav-count neutral">{projects.length}</span>}
        </button>
        <div className="sidebar-bottom">
          <div className="local-callout">
            <ShieldCheck size={19} />
            <div>
              <strong>{health?.ai_configured ? 'Local storage · AI sees selected excerpts only (store=false)' : 'Fully local · no AI calls'}</strong>
              <p>
                {health?.ai_configured
                  ? 'AI interprets selected excerpts. You control every decision.'
                  : 'Local parsing is available. Connect AI when you need it.'}
              </p>
            </div>
          </div>
        </div>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <img className="mobile-equans-logo" src="/brand/equans-switzerland.svg" alt="Equans Switzerland" width="120" height="37" />
          <div className="breadcrumb">
            <span>{page === 'management' ? 'Organization' : 'Tender workspace'}</span>
            <span>/</span>
            <strong>{page === 'management' ? 'Management' : page === 'workspace' ? 'My workspace' : project ? project.name : 'New estimate'}</strong>
          </div>
          <div className="header-right">
            <LanguageSelector />
            {project && page !== 'management' && page !== 'workspace' && (
              <Badge tone="neutral">
                <span className="live-dot" /> Revision {project.revision} saved
              </Badge>
            )}
            <button className="connection-status" aria-label={health?.ai_configured ? 'AI configured' : 'Local mode'} title={health?.ai_configured ? 'AI configured' : 'Local mode'} onClick={() => setRunOptionsOpen(true)}>
              <span className={`connection-dot ${health ? 'connected' : ''}`} />
              {health?.ai_configured ? 'AI configured' : 'Local mode'}
              <ChevronDown size={12} />
            </button>
            <div className="profile-menu-wrap">
              <button className="header-avatar profile-trigger" aria-label="Open profile menu" onClick={() => setProfileOpen(v => !v)}>{actor.split(' ').map(x => x[0]).join('').slice(0, 2).toUpperCase()}</button>
              {profileOpen && <div className="profile-menu"><strong>{actor}</strong><small>{role}</small><button onClick={() => setProfileOpen(false)}>Manage profile</button><button onClick={() => { localStorage.removeItem('bidgenius_session'); setLoggedIn(false); setProfileOpen(false); }}>Sign out</button></div>}
            </div>
          </div>
        </header>
        {project && page !== 'management' && page !== 'workspace' && (
          <div className="projectbar">
            <div>
              <span className="project-icon">
                <Building2 size={20} />
              </span>
              <div>
                <strong>{project.name}</strong>
                <span>
                  {project.document.filename} · {project.document.page_count} pages · BKP 244
                </span>
              </div>
              <div className={`bid-status-control bid-status-${project.bid_status || 'draft'}`}>
                <span className="bid-status-dot" />
                <select
                  aria-label="Bid status"
                  value={project.bid_status || 'draft'}
                  disabled={statusBusy}
                  onChange={(e) => void changeBidStatus(e.target.value as BidStatus)}
                >
                  {(role === 'Management' ? managementStatuses : estimatorStatuses).map((status) => (
                    <option key={status} value={status}>
                      {statusLabels[status]}
                    </option>
                  ))}
                </select>
                <ChevronDown size={13} />
              </div>
              {pinnedDemo?.project_id === project.id && pinnedDemo.prepared_at && (
                <Badge tone="blue">Prepared demo · {date(pinnedDemo.prepared_at)}</Badge>
              )}
            </div>
            <div className="inline">
              <button className="text-btn" onClick={() => setProcessingOpen(true)}>
                <Activity size={14} />
                {activeRun(run) ? 'Processing…' : run?.completed_at ? 'Processing record' : 'Run details'}
              </button>
              {page !== 'export' && (
                <Button variant="primary" onClick={() => setPage('export')}>
                  <FileCheck2 size={15} /> Export estimate
                </Button>
              )}
            </div>
          </div>
        )}
        {error && (
          <div className="global-error">
            <ErrorBox message={error} />
            <button className="icon-btn" aria-label="Dismiss error" onClick={() => setError('')}>
              <X size={16} />
            </button>
          </div>
        )}
        {page === 'management' && role === 'Management' ? (
          <Management loading={managementLoading} bids={managementBids} loadError={managementError} onRetry={() => setManagementRetry(n => n + 1)} initialEstimator={workspaceEstimator} onOpen={loadProject} onDuplicate={() => void duplicateVariant()} />
        ) : page === 'workspace' ? (
          <Workspace projects={projects} actor={actor} loading={booting} busy={busy} onOpen={async id => { await loadProject(id); if (projectRef.current?.id === id) setPage('estimate'); }} onAdd={() => setImportOpen(true)} />
        ) : booting ? (
          <div className="boot-state">
            <Spinner text="Opening your local workspace…" />
          </div>
        ) : !project ? (
          <Welcome
            busy={busy}
            useAI={useAI}
            setUseAI={setUseAI}
            health={health}
            onDemo={() => void openDemo()}
            onImport={() => setImportOpen(true)}
          />
        ) : (
          <>
            {activeRun(run) && (
              <div className="run-banner">
                <LoaderCircle size={16} className="spin" />
                <div>
                  <strong>{runStageLabel(run!)}</strong>
                  <span>
                    {reviewingGaps(run!)
                      ? `${run!.ai_batches_done}/${run!.ai_batches_total} AI review batches · ${run!.local_positions_found ?? run!.positions_found} positions found locally`
                      : `${run!.pages_processed}/${run!.total_pages} pages · ${run!.batches_done}/${run!.batches_total} ${hybridRun(run!) ? 'local ' : ''}batches`}
                  </span>
                </div>
                <div className="progress-track" role="progressbar" aria-label={reviewingGaps(run!) ? 'AI review progress' : 'Document extraction progress'} aria-valuenow={Math.round(runProgress(run!))} aria-valuemin={0} aria-valuemax={100}>
                  <div
                    style={{
                      width: `${runProgress(run!)}%`,
                    }}
                  />
                </div>
                <Button variant="ghost" onClick={() => setProcessingOpen(true)}>
                  View progress <ArrowRight size={14} />
                </Button>
              </div>
            )}
            {['failed', 'cancelled', 'resumable'].includes(run?.status || '') && (
              <div className="run-banner warning">
                <TriangleAlert size={17} />
                <span>Processing {label(run!.status).toLowerCase()}. Completed work has been retained.</span>
                <Button onClick={() => onResume('continue')}>
                  <RotateCcw size={14} /> Resume
                </Button>
              </div>
            )}
            {summary ? (
              <>
                {page === 'overview' && (
                  <Overview
                    summary={summary}
                    onEstimate={(cause) => {
                      setInitialCause(cause || 'all');
                      setPage('estimate');
                    }}
                    onScenarios={() => setPage('scenarios')}
                    onAnalytics={() => setPage('analytics')}
                    onAssumptions={() => setAssumptionsOpen(true)}
                    onAdjustment={(a) => setAdjustmentEdit(a)}
                    onReviewAdjustment={onReviewAdjustment}
                    onIssue={setIssueOpen}
                    onSource={(p) => {
                      setSelectedId(null);
                      setSourcePage(p);
                      setPage('estimate');
                    }}
                    onRequirement={(r) =>
                      setReasonTask({
                        title: 'Review tender requirement',
                        description: r.title,
                        submit: (reason) =>
                          mutate(`/projects/${project!.id}/requirements/${r.id}`, {
                            reason,
                            changes: { review_state: 'accepted' },
                          }),
                      })
                    }
                  />
                )}
                {page === 'analytics' && <Analytics summary={summary} onEstimate={() => { setInitialCause('all'); setPage('estimate'); }} onScenarios={() => setPage('scenarios')} />}
                {page === 'estimate' && (
                  <Estimate
                    positions={positions}
                    document={project.document}
                    projectId={project.id}
                    revision={project.revision}
                    selectedId={selectedId}
                    onSelect={select}
                    onEdit={setPositionEdit}
                    onAccept={onAccept}
                    onManual={setManualSpans}
                    onUndo={onUndo}
                    onBulkAreaRule={onBulkAreaRule}
                    history={summary.history}
                    references={references}
                    sourcePage={sourcePage}
                    initialCause={initialCause}
                    mutate={mutate}
                  />
                )}
                {page === 'scenarios' && (
                  <ScenarioPage
                    key={`${project.id}-${project.revision}`}
                    project={project}
                    summary={summary}
                    mutate={mutate}
                  />
                )}
                {page === 'export' && <ExportPage project={project} summary={summary} onUndo={onUndo} />}
              </>
            ) : (
              <Spinner text="Preparing your estimate workspace…" />
            )}
          </>
        )}
        {busy && project && (
          <div className="busy-indicator">
            <LoaderCircle size={15} className="spin" /> Updating workspace…
          </div>
        )}
      </main>
      {toast && (
        <div role="status" className="toast">
          <span>
            <Check size={17} />
          </span>
          {toast}
          <button className="icon-btn" aria-label="Dismiss notification" onClick={() => setToast('')}>
            <X size={15} />
          </button>
        </div>
      )}
      {positionEdit && (
        <PositionDialog
          position={positionEdit}
          references={references}
          onClose={() => setPositionEdit(null)}
          mutate={mutate}
        />
      )}
      {manualSpans && project && (
        <ManualDialog
          spans={manualSpans}
          project={project}
          onClose={() => setManualSpans(null)}
          mutate={(p, b) => mutate(p, b, 'POST')}
          onSelect={select}
        />
      )}
      {assumptionsOpen && project && (
        <AssumptionsDialog project={project} onClose={() => setAssumptionsOpen(false)} mutate={mutate} />
      )}
      {adjustmentEdit !== null && project && (
        <AdjustmentDialog
          project={project}
          adjustment={adjustmentEdit}
          onClose={() => setAdjustmentEdit(null)}
          mutate={mutate}
        />
      )}
      {reasonTask && (
        <ReasonDialog
          title={reasonTask.title}
          description={reasonTask.description}
          delta={reasonTask.delta}
          onClose={() => setReasonTask(null)}
          onSubmit={reasonTask.submit}
        />
      )}
      <Assistant
        project={project}
        page={page}
        selectedPositionId={selectedId}
        offline={!health?.ai_configured}
        onAction={(action) => {
          const target = action.payload?.page;
          if (target && typeof target === 'string') setPage(target as Page);
          const positionId = action.payload?.position_id;
          if (positionId && typeof positionId === 'string') { setSelectedId(positionId); setPage('estimate'); }
          if (action.type === 'open_pdf_page' && typeof action.payload?.page === 'number') { setSourcePage(action.payload.page); setPage('estimate'); }
        }}
      />
      {importOpen && (
        <ImportDialog
          health={health}
          useAI={useAI}
          setUseAI={setUseAI}
          onClose={() => setImportOpen(false)}
          onLoaded={async (id) => {
            await loadProject(id);
            setProjects(await api<Project[]>('/projects'));
            setProcessingOpen(true);
          }}
        />
      )}
      <Modal
        open={projectsOpen}
        onClose={() => setProjectsOpen(false)}
        title="Saved projects"
        description="Projects and estimate revisions persist on this computer."
      >
        <div className="modal-body saved-projects">
          {projects.length === 0 ? (
            <p>No projects yet. Import a package or load Oberglatt to get started.</p>
          ) : (
            projects.map((p) => (
              <button key={p.id} onClick={() => void loadProject(p.id)}>
                <span className="project-icon">
                  <Building2 size={19} />
                </span>
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {pinnedDemo?.project_id === p.id && pinnedDemo.prepared_at
                      ? `Prepared demo · ${date(pinnedDemo.prepared_at)} · `
                      : ''}
                    Revision {p.revision} · {date(p.updated_at)}
                  </small>
                </div>
                <ArrowRight size={17} />
                <button className="text-btn" onClick={(e) => { e.stopPropagation(); void duplicateVariant(p.id); }}>Duplicate as variant</button>
              </button>
            ))
          )}
        </div>
        <div className="modal-footer">
          <Button
            onClick={() => {
              setProjectsOpen(false);
              setImportOpen(true);
            }}
          >
            <Plus size={15} /> Import project
          </Button>
        </div>
      </Modal>
      <Modal
        open={processingOpen}
        onClose={() => setProcessingOpen(false)}
        title="Processing record"
        description="Saved progress and results from this processing run."
      >
        <div className="modal-body">
          {run ? (
            <>
              <div className="inline">
                <Status status={run.status} />
                <Badge tone="blue">{extractionModeLabel(run)}</Badge>
              </div>
              <h3>{runStageLabel(run)}</h3>
              <div className="run-metrics">
                <div>
                  <strong>
                    {run.pages_processed}/{run.total_pages}
                  </strong>
                  <span>Pages processed</span>
                </div>
                <div>
                  <strong>
                    {run.batches_done}/{run.batches_total}
                  </strong>
                  <span>{hybridRun(run) ? 'Local batches completed' : 'Batches completed'}</span>
                </div>
                <div>
                  <strong>{run.positions_found}</strong>
                  <span>Positions recorded in this run</span>
                </div>
              </div>
              <p className="text-muted">Each local batch contains up to 4 pages from the same system section.</p>
              {hybridRun(run) && <RunPhases run={run} />}
              {summary && <p className="text-muted">
                Current estimate: {summary.coverage.positions_extracted + summary.coverage.positions_manual} positions
                {' '}({summary.coverage.positions_manual} added manually). The run count is a saved snapshot; later edits appear in Overview.
              </p>}
              <p className="text-muted">
                Started {date(run.started_at)}
                {run.completed_at && ` · Completed ${date(run.completed_at)}`}
              </p>
              {run.duration_seconds !== undefined && run.duration_seconds !== null && (
                <p>Measured processing time: {Number(run.duration_seconds).toFixed(1)} seconds.</p>
              )}
              {run.model && <p>{hybridRun(run) && !usageCount(run, 'successful_ai_batches')
                ? usageCount(run, 'cached_ai_batches') ? 'Model from cached review' : 'Configured review model'
                : 'Model used'}: {run.model}</p>}
              {run.extraction_mode === 'local' && <p className="text-muted">AI was not enabled for this run.</p>}
              <details>
                <summary>Processing usage</summary>
                <p className="text-muted">Local and cached batches describe processing work. Tokens measure text sent to and returned by the AI model.</p>
                <div className="audit-list">
                  {Object.entries(run.usage).map(([key, value]) => <div key={key}>
                    <strong>{usageLabels[key] || label(key)}</strong>
                    <span>{value && typeof value === 'object'
                      ? Array.isArray(value) ? `${value.length} entries` : Object.entries(value).map(([name, item]) => `${label(name)}: ${String(item)}`).join(' · ')
                      : String(value)}</span>
                  </div>)}
                </div>
              </details>
              {run.errors.length > 0 && <ErrorBox message={run.errors.join('\n')} />}
              <div className="note">
                Completed runs are previously processed results. Local edits, recalculation, and export remain
                available offline.
              </div>
            </>
          ) : (
            <p>No processing run recorded.</p>
          )}
        </div>
        <div className="modal-footer">
          {activeRun(run) ? (
            <Button
              variant="danger"
              onClick={async () => {
                try {
                  await post(`/runs/${run!.id}/cancel`);
                  setToast('Cancellation requested at the next safe boundary.');
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <Square size={13} /> Stop processing
            </Button>
          ) : run?.status === 'awaiting_review' ? (
            <Button
              variant="primary"
              onClick={() => {
                setProcessingOpen(false);
                onResume('complete_review');
              }}
            >
              <Check size={15} /> Complete review
            </Button>
          ) : run && ['failed', 'cancelled', 'resumable'].includes(run.status) ? (
            <Button
              onClick={() => {
                setProcessingOpen(false);
                onResume('continue');
              }}
            >
              <RotateCcw size={15} /> Resume saved run
            </Button>
          ) : (
            <Button
              onClick={() => {
                setProcessingOpen(false);
                setRunOptionsOpen(true);
              }}
            >
              Process again
            </Button>
          )}
          <Button onClick={() => setProcessingOpen(false)}>Close</Button>
        </div>
      </Modal>
      <Modal
        open={runOptionsOpen}
        onClose={() => setRunOptionsOpen(false)}
        title="Processing options"
        description="Extract the full document locally, with optional AI review of unresolved items. Calculations always run locally."
      >
        <div className="modal-body">
          <div className="mode-option">
            <HardDrive size={20} />
            <div>
              <strong>1. Local document extraction</strong>
              <p>
                Extract supported schedules without an external service. Ambiguous scope stays visible for
                review.
              </p>
            </div>
            <Badge tone="green">Available</Badge>
          </div>
          <AIReviewOption health={health} checked={useAI} onChange={setUseAI} />
          {!health?.ai_configured && (
            <div className="note">
              To enable AI, set OPENAI_API_KEY in the local .env file and restart the server. The key never
              enters the browser.
            </div>
          )}
          {health?.ai_configured && <p className="text-muted">Configured model: {health.model}</p>}
          {project && (
            <div className="note">
              A new run reprocesses source positions. Recorded estimator decisions remain in the project
              history.
            </div>
          )}
        </div>
        <div className="modal-footer">
          <Button onClick={() => setRunOptionsOpen(false)}>Close</Button>
          {project && (
            <Button variant="primary" disabled={busy || activeRun(run)} onClick={() => void onStartRun()}>
              <RotateCcw size={15} /> Start processing
            </Button>
          )}
        </div>
      </Modal>
      {issueOpen && (
        <IssueDialog
          issue={issueOpen}
          documentId={project?.document.id || ''}
          onClose={() => setIssueOpen(null)}
          onSource={(p) => {
            setSourcePage(p);
            setSelectedId(issueOpen.position_ids[0] || null);
            setIssueOpen(null);
            setPage('estimate');
          }}
          onAccept={() => {
            const issue = issueOpen;
            setIssueOpen(null);
            setReasonTask({
              title: 'Resolve review issue',
              description: issue.title,
              submit: (reason) =>
                mutate(`/projects/${project!.id}/issues/${issue.id}`, {
                  reason,
                  changes: { review_state: 'accepted' },
                }),
            });
          }}
          onScopeDecision={(choice) => {
            const issue = issueOpen;
            setIssueOpen(null);
            const changes = choice === 'exclude'
              ? { status: 'out_of_scope' }
              : choice === 'install_only'
                ? { pricing_basis: 'labour_only', overrides: { labour_only: true }, status: 'assumption_applied' }
                : { status: 'assumption_applied' };
            setReasonTask({
              title: 'Resolve scope ambiguity',
              description: choice === 'include' ? 'Include: supply and install' : choice === 'install_only' ? 'Install only: labour; material zero' : 'Exclude: by others',
              submit: (reason) => mutate(`/positions/${issue.position_ids[0]}`, { reason, changes }),
            });
          }}
        />
      )}
    </div>
  );
}
function RunPhases({ run }: { run: Run }) {
  const localComplete = run.local_positions_found !== null && run.local_positions_found !== undefined;
  const successful = usageCount(run, 'successful_ai_batches');
  const failed = usageCount(run, 'failed_ai_batches');
  const cached = usageCount(run, 'cached_ai_batches');
  const reviewSummary = !localComplete
    ? 'Waiting for local extraction to finish.'
    : !run.ai_batches_total
      ? activeRun(run)
        ? 'Selecting unresolved items for AI review.'
        : ['complete', 'awaiting_review'].includes(run.status)
          ? 'No unresolved items eligible for AI review. No AI calls were made.'
          : 'AI review has not started. No AI calls were made.'
      : failed && !successful && !cached && !activeRun(run)
        ? 'AI review did not complete successfully. Local results are retained.'
        : `${run.ai_batches_done}/${run.ai_batches_total} review batches completed. ${successful} successful calls, ${cached} reused from cache, ${failed} failed.`;
  return (
    <ol className="run-phases" aria-label="Processing phases">
      <li>
        <strong>1. Local extraction</strong>
        <p>{run.batches_done}/{run.batches_total} batches processed across the full document.</p>
        <span>{localComplete ? `${run.local_positions_found} positions found locally` : 'Identifying positions without AI'}</span>
      </li>
      <li>
        <strong>2. AI review of unresolved items</strong>
        <p>{reviewSummary}</p>
        {run.ai_batches_total > 0 && <>
          <span>{usageCount(run, 'ai_review_positions')} unresolved positions · {usageCount(run, 'ai_review_source_blocks')} source blocks selected</span>
          <span>{usageCount(run, 'ai_positions_added')} positions added · {usageCount(run, 'ai_positions_refined')} AI refinements for review</span>
        </>}
        <p>Only extraction gaps go to AI with relevant source excerpts, local findings, and the missing details. AI results require estimator review.</p>
      </li>
    </ol>
  );
}
function AIReviewOption({ health, checked, onChange }: {
  health: Health | null;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const descriptionId = useId();
  const available = supportsSelectiveAI(health);
  return (
    <label className={`mode-option ${!available ? 'unavailable' : ''}`}>
      <Sparkles size={20} aria-hidden="true" />
      <div>
        <strong>Review unresolved items with AI</strong>
        <p id={descriptionId}>{health?.ai_configured && !available
          ? 'Restart the app after the current run finishes to enable AI review of unresolved items.'
          : 'First extract the full document locally. Then send only unidentified or incomplete items, relevant source excerpts, and local findings to AI. Clear items stay local.'}</p>
      </div>
      <input
        type="checkbox"
        aria-label="Review unresolved items with AI"
        aria-describedby={descriptionId}
        checked={checked && available}
        onChange={(e) => onChange(e.target.checked)}
        disabled={!available}
      />
    </label>
  );
}
function Welcome({
  busy,
  useAI,
  setUseAI,
  health,
  onDemo,
  onImport,
}: {
  busy: boolean;
  useAI: boolean;
  setUseAI: (v: boolean) => void;
  health: Health | null;
  onDemo: () => void;
  onImport: () => void;
}) {
  return (
    <div className="welcome-page">
      <div className="welcome-copy">
        <Badge tone="blue">
          <ShieldCheck size={12} /> BUILT FOR THE ESTIMATOR
        </Badge>
        <h1>
          From tender
          <br />
          to <span>defensible offer.</span>
        </h1>
        <p className="welcome-description">
          Turn complex tender documents into a transparent first estimate. Trace every number, resolve
          uncertainty, and make the commercial decisions that matter.
        </p>
        <div className="welcome-actions">
          <Button variant="primary" disabled={busy || !health} onClick={onDemo}>
            {busy ? <LoaderCircle className="spin" size={18} /> : <FolderOpen size={18} />}{' '}
            {busy ? 'Opening Oberglatt…' : 'Explore the Oberglatt tender'}
            <ArrowRight size={17} />
          </Button>
          <Button onClick={onImport}>
            <Upload size={17} /> Import package
          </Button>
        </div>
        {health?.ai_configured && <AIReviewOption health={health} checked={useAI} onChange={setUseAI} />}
        <div className="welcome-trust">
          <span>
            <HardDrive size={15} /> Local-first workspace
          </span>
          <span>
            <ShieldCheck size={15} /> Evidence at every step
          </span>
        </div>
      </div>
      <div className="welcome-visual">
        <div className="blueprint-top">
          <span>
            <Building2 size={16} /> PRIMARY SCHOOL OBERGLATT
          </span>
          <Badge tone="blue">BKP 244</Badge>
        </div>
        <svg
          viewBox="0 0 480 270"
          className="building-drawing"
          role="img"
          aria-label="Architectural line illustration of a school building"
        >
          <defs>
            <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--border)" strokeWidth=".6" />
            </pattern>
          </defs>
          <rect width="480" height="270" fill="url(#grid)" />
          <g fill="none" stroke="var(--brand-navy-2)" strokeWidth="1.4">
            <path d="M70 175 280 215 420 139 207 103Z" fill="var(--bg)" />
            <path d="M70 175V85L280 125V215M280 125 420 49V139M70 85 210 12 420 49M210 12V103" />
            <path d="M70 85 280 125 420 49M70 114 280 154 420 78M70 145 280 185 420 109" />
            <path
              d="M87 98 120 104V121L87 115ZM134 107 167 113V130L134 124ZM181 116 214 122V139L181 133ZM228 125 261 131V148L228 142ZM87 131 120 137V152L87 146ZM134 140 167 146V161L134 155ZM181 149 214 155V170L181 164ZM228 158 261 164V179L228 173Z"
              fill="var(--brand-green-tint)"
            />
            <path
              d="M294 130 323 114V135L294 151ZM339 105 368 89V110L339 126ZM384 80 408 67V88L384 101ZM294 162 323 146V166L294 182ZM339 137 368 121V141L339 157ZM384 112 408 99V119L384 132Z"
              fill="var(--brand-green-tint)"
            />
            <path d="M206 83 245 63 292 72 253 93Z" fill="var(--brand-green-soft)" />
            <path d="M206 83V65L245 45 292 54V72M206 65 253 75 292 54M253 75V93" />
            <path d="M152 84 152 70 170 61 198 66V80M152 70 180 76 198 66M180 76V90" />
            <path
              d="M35 210 280 255 457 161M45 204V216M280 248V261M451 156 461 168"
              stroke="var(--muted)"
              strokeDasharray="4 3"
            />
          </g>
          <g fill="var(--muted)" fontSize="12" fontFamily="Roboto">
            <text x="115" y="239">
              VENTILATION SYSTEMS
            </text>
            <text x="335" y="223">
              EVIDENCE-LED TAKEOFF
            </text>
          </g>
          <circle cx="272" cy="67" r="6" fill="var(--accent)" stroke="white" strokeWidth="3" />
        </svg>
        <div className="blueprint-evidence">
          <span className="evidence-check">
            <Check size={18} />
          </span>
          <div>
            <strong>Source → quantity → price</strong>
            <span>One connected, reviewable estimate</span>
          </div>
          <ArrowRight size={18} />
        </div>
        <div className="document-tabs">
          <span>
            <FileText size={14} /> Original tender
          </span>
          <span>
            <LayersIcon /> Catalogue
          </span>
          <span>
            <Gauge size={14} /> Installation rules
          </span>
        </div>
      </div>
      <div className="welcome-process">
        {[
          {
            n: '01',
            icon: FileInput,
            title: 'Understand the scope',
            text: 'Process the full tender and preserve original German evidence.',
          },
          {
            n: '02',
            icon: Table2,
            title: 'Build the estimate',
            text: 'Connect catalogue references, installation rules, and transparent costs.',
          },
          {
            n: '03',
            icon: ShieldCheck,
            title: 'Review with confidence',
            text: 'Resolve contradictions, record assumptions, and export the proof.',
          },
        ].map((s) => (
          <div key={s.n}>
            <div className="process-step">
              <s.icon size={20} />
              <span>{s.n}</span>
            </div>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </div>
      <div className="welcome-footer">
        <span>BIDGENIUS AI · ESTIMATOR WORKSPACE</span>
        <span>Local infrastructure. Human judgment.</span>
      </div>
    </div>
  );
}
function LayersIcon() {
  return <FolderOpen size={14} />;
}
function ImportDialog({
  health,
  useAI,
  setUseAI,
  onClose,
  onLoaded,
}: {
  health: Health | null;
  useAI: boolean;
  setUseAI: (checked: boolean) => void;
  onClose: () => void;
  onLoaded: (id: string) => Promise<void>;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      open
      onClose={onClose}
      title="Import a tender package"
      description="Choose the ZIP package, or the PDF and reference files together."
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          const body = new FormData();
          files.forEach((f) => body.append('files', f));
          body.append('use_ai', String(useAI && supportsSelectiveAI(health)));
          try {
            const result = await api<{ project_id: string }>('/projects/import', { method: 'POST', body });
            await onLoaded(result.project_id);
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="modal-body">
          {error && <ErrorBox message={error} />}
          <label className="upload-zone">
            <Upload size={32} />
            <strong>Choose your tender files</strong>
            <span>ZIP, PDF, catalogue CSV, productivity CSV, project JSON</span>
            <input
              type="file"
              multiple
              accept=".zip,.pdf,.csv,.json"
              required
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
            />
          </label>
          {files.map((f) => (
            <div className="selected-file" key={f.name}>
              <FileText size={15} />
              <span>{f.name}</span>
              <small>{(f.size / 1024).toFixed(0)} KB</small>
            </div>
          ))}
          <AIReviewOption health={health} checked={useAI} onChange={setUseAI} />
          {!health?.ai_configured && <p className="text-muted">AI is not configured. This package will be processed locally.</p>}
          <div className="note">
            Original files remain unchanged. The server validates the package before local extraction begins.
          </div>
        </div>
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!files.length || busy}>
            {busy ? 'Importing…' : 'Import and process'}
            <ArrowRight size={15} />
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function IssueDialog({
  issue,
  documentId,
  onClose,
  onSource,
  onAccept,
  onScopeDecision,
}: {
  issue: Issue;
  documentId: string;
  onClose: () => void;
  onSource: (page: number) => void;
  onAccept: () => void;
  onScopeDecision: (choice: 'include' | 'install_only' | 'exclude') => void;
}) {
  const [sources, setSources] = useState<SourceSpan[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    Promise.all(issue.source_span_ids.slice(0, 6).map((id) => api<SourceSpan>(`/sources/${id}`)))
      .then((s) => {
        if (alive) setSources(s);
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      });
    return () => {
      alive = false;
    };
  }, [issue.id]);
  return (
    <Modal open onClose={onClose} title={issue.title} description={issue.action} wide>
      <div className="modal-body">
        <div className="inline">
          <Status status={issue.severity} />
          <Badge>{label(issue.kind)}</Badge>
          <Status status={issue.review_state} />
        </div>
        <p>{issue.detail}</p>
        {issue.kind === 'scope_ambiguity' && (
          <div className="inline">
            <Button variant="primary" onClick={() => onScopeDecision('include')}>Include (supply + install)</Button>
            <Button onClick={() => onScopeDecision('install_only')}>Install only (labour)</Button>
            <Button variant="danger" onClick={() => onScopeDecision('exclude')}>Exclude (by others)</Button>
          </div>
        )}
        {error && <ErrorBox message={error} />}
        <h4>Source evidence</h4>
        {sources.length ? (
          sources.map((s) => (
            <div className="issue-source" key={s.id}>
              <div className="source-quote">{s.text}</div>
              <div className="inline">
                <Button variant="ghost" onClick={() => onSource(s.page)}>
                  <FileText size={14} /> Inspect page {s.page}
                  <ArrowRight size={13} />
                </Button>
                <a
                  className="text-btn"
                  target="_blank"
                  rel="noreferrer"
                  href={`/api/documents/${documentId}/file#page=${s.page}`}
                >
                  Original PDF
                </a>
              </div>
            </div>
          ))
        ) : (
          <p className="text-muted">
            {issue.source_span_ids.length
              ? 'Loading evidence…'
              : 'This issue refers to package completeness or an estimator assumption.'}
          </p>
        )}
      </div>
      <div className="modal-footer">
        <Button onClick={onClose}>Leave unresolved</Button>
        <Button variant="primary" onClick={onAccept} disabled={issue.review_state === 'accepted'}>
          <Check size={15} /> Mark reviewed
        </Button>
      </div>
    </Modal>
  );
}
