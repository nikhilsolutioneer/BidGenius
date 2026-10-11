import { ArrowRight, FileText, Plus, Search } from 'lucide-react';
import { useState } from 'react';
import { date } from './api';
import { Button, Spinner } from './components';
import type { Project } from './types';

const labels = { draft: 'Draft', in_review: 'Pending review', approved: 'Approved', submitted: 'Submitted' };

export default function Workspace({ projects, actor, loading, busy, onOpen, onAdd }: {
  projects: Project[]; actor: string; loading: boolean; busy: boolean;
  onOpen: (id: string) => void; onAdd: () => void;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const owned = projects.filter(p => (p.estimator || 'Local estimator').trim().toLowerCase() === actor.trim().toLowerCase());
  const visible = owned.filter(p => p.name.toLowerCase().includes(query.toLowerCase()) && (!status || (p.bid_status || 'draft') === status))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return <section className="estimator-workspace" aria-busy={loading || busy}>
    <div className="workspace-heading"><div><span className="eyebrow">MY WORKSPACE</span><h1>Your projects</h1><p>{actor} · {owned.length} projects. Select a project to continue estimating.</p></div><Button variant="primary" onClick={onAdd}><Plus size={18} /> New project</Button></div>
    <div className="workspace-filters"><label className="workspace-search"><Search size={17} aria-hidden="true" /><input aria-label="Search your projects" placeholder="Search projects…" value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label="Filter projects by status" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    {loading ? <Spinner text="Loading your projects…" /> : <>
      {busy && <div role="status"><Spinner text="Opening estimate…" /></div>}
      {visible.length ? <div className="workspace-projects">{visible.map(p => <button className="workspace-project" key={p.id} disabled={busy} onClick={() => onOpen(p.id)}>
        <div className="workspace-project-top"><span className="project-icon"><FileText size={21} /></span><span className={`workspace-status workspace-status-${p.bid_status || 'draft'}`}>{labels[p.bid_status || 'draft']}</span></div>
        <h2>{p.name}</h2><p>{p.document?.filename || 'Tender project'}</p>
        <div className="workspace-project-footer"><span>Updated {date(p.updated_at)}<small>Revision {p.revision}</small></span><ArrowRight size={18} aria-hidden="true" /></div>
      </button>)}</div> : <div className="panel workspace-empty"><FileText size={32} aria-hidden="true" /><h2>{owned.length ? 'No matching projects' : 'Start your first estimate'}</h2><p>{owned.length ? 'Try another search or status filter.' : 'Add a tender to create a project in your workspace.'}</p>{!owned.length && <Button variant="primary" onClick={onAdd}><Plus size={17} /> New project</Button>}</div>}
    </>}
  </section>;
}
