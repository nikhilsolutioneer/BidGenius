import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ExternalLink, History as HistoryIcon } from 'lucide-react';
import { api, date, label, money, number } from './api';
import { Badge, Button, Modal, Spinner } from './components';
import HistoryChanges, { historyTarget } from './HistoryChanges';
import type { History } from './types';
export type Bid = { id:string; name:string; estimator:string; bid_status:string; updated_at:string; offer_price:string|null; target_margin_pct:string; pct_value_priced:string; pending_reviews:number; unpriced_allowance_low:string; unpriced_allowance_high:string; scenarios:Record<string,string> };
const statuses=['draft','in_review','approved','submitted'];
const statusLabels: Record<string, string> = { draft: 'Draft', in_review: 'In review', approved: 'Approved', submitted: 'Submitted' };
type ManagementProps = { loading:boolean; bids:Bid[]|null; loadError:string; onRetry:()=>void; initialEstimator?:string; onOpen:(id:string)=>void; onDuplicate:()=>void };
type Audit = { project_id:string; project_name:string; revision:number; updated_at:string; estimator:string; bid_status:string; history:History[] };
function StatusChart({ bids }: { bids: Bid[] }) {
 const [table, setTable] = useState(false);
 const [active, setActive] = useState<string | null>(null);
 const colors = ['var(--viz-context)', 'var(--brand-navy)', 'var(--brand-green-ink)', 'var(--brand-green)'];
 let offset = 0;
 const slices = statuses.map((status, i) => {
   const matches = bids.filter(b => b.bid_status === status);
   const share = bids.length ? matches.length / bids.length * 100 : 0;
   const slice = { status, count: matches.length, share, offset, color: colors[i], value: matches.reduce((sum, b) => sum + Number(b.offer_price || 0), 0) };
   offset += share;
   return slice;
 });
 const selected = slices.find(slice => slice.status === active);
 return <section className="panel management-chart">
   <div className="panel-header"><h2>Bids by status</h2><button className="text-btn" aria-label={table ? 'Show status chart' : 'Show status table'} onClick={() => setTable(!table)}>{table ? 'Chart' : 'Table'}</button></div>
   {table ? <div className="status-data-table"><table><thead><tr><th>Status</th><th>Bids</th><th>Share</th><th>Offer value</th></tr></thead><tbody>{slices.map(slice => <tr key={slice.status}><td>{statusLabels[slice.status]}</td><td>{slice.count}</td><td>{number(slice.share, 1)}%</td><td>{money(slice.value)}</td></tr>)}</tbody></table></div> : <>
     <div className="status-chart-layout">
       <svg viewBox="0 0 180 180" aria-label={`Bids by status: ${bids.length} bids`}>
         <circle cx="90" cy="90" r="63" fill="none" stroke="var(--border)" strokeWidth="24" />
         {slices.filter(slice => slice.count > 0).map(slice => <circle key={slice.status} cx="90" cy="90" r="63" fill="none" stroke={slice.color} strokeWidth={active === slice.status ? 29 : 24} pathLength="100" strokeDasharray={`${slice.share} ${100 - slice.share}`} strokeDashoffset={-slice.offset} transform="rotate(-90 90 90)" tabIndex={0} role="img" aria-label={`${statusLabels[slice.status]}: ${slice.count} bids, ${number(slice.share, 1)}%, ${money(slice.value)}`} onMouseEnter={() => setActive(slice.status)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(slice.status)} onBlur={() => setActive(null)}><title>{statusLabels[slice.status]}: {slice.count} bids · {money(slice.value)}</title></circle>)}
         <text x="90" y="89" textAnchor="middle" fill="var(--text)" fontSize="28" fontWeight="700">{bids.length}</text>
         <text x="90" y="109" textAnchor="middle" fill="var(--muted)" fontSize="12">{bids.length ? 'Total bids' : 'No bids'}</text>
       </svg>
       <ul className="status-chart-legend">{slices.map(slice => <li key={slice.status}><span className="status-chart-swatch" style={{ background: slice.color }} /><span>{statusLabels[slice.status]}</span><strong>{slice.count}</strong><small>{number(slice.share, 1)}%</small></li>)}</ul>
     </div>
     <div className="status-chart-detail" aria-live="polite">{selected ? `${statusLabels[selected.status]} · ${selected.count} bids · ${money(selected.value)}` : 'Hover or focus a segment to see its offer value'}</div>
   </>}
 </section>;
}
export default function Management(props: ManagementProps) {
 return <section className="management-container" aria-busy={props.loading}>
   {props.loading && props.bids && <div className="management-refresh" role="status"><Spinner text="Updating bids…" /></div>}
   <BidDashboard {...props} />
 </section>;
}
function BidDashboard({ bids: cachedBids, loadError, onRetry, initialEstimator, onOpen, onDuplicate }: ManagementProps) {
 const bids = cachedBids || [];
 const [est,setEst]=useState(initialEstimator || ''); const [status,setStatus]=useState(''); const [sort,setSort]=useState('offer_price'); const [table,setTable]=useState<Record<string,boolean>>({});
 const [selectedBid,setSelectedBid]=useState<string|null>(null); const [audit,setAudit]=useState<Audit|null>(null); const [auditLoading,setAuditLoading]=useState(false); const [auditError,setAuditError]=useState('');
 useEffect(()=>{ setEst(initialEstimator || ''); },[initialEstimator]);
 const rows=useMemo(()=>bids.filter(b=>(!est||b.estimator===est)&&(!status||b.bid_status===status)).sort((a,b)=>String(b[sort as keyof Bid]??'').localeCompare(String(a[sort as keyof Bid]??''),undefined,{numeric:true})),[bids,est,status,sort]);
 const sum=(xs:Bid[])=>xs.reduce((n,b)=>n+Number(b.offer_price||0),0); const avg=(key:keyof Bid)=>rows.length?rows.reduce((n,b)=>n+Number(b[key]||0),0)/rows.length:0;
 const auditRequest = useRef(0);
 const selectAudit = async (id:string) => {
   const request = ++auditRequest.current;
   setSelectedBid(id); setAudit(null); setAuditError(''); setAuditLoading(true);
   try { const result = await api<Audit>(`/admin/bids/${id}/audit`); if (request === auditRequest.current) setAudit(result); }
   catch (e) { if (request === auditRequest.current) setAuditError((e as Error).message); }
   finally { if (request === auditRequest.current) setAuditLoading(false); }
 };
 if (loadError) return <div className="management-page"><h1>Bid pipeline</h1><p role="alert">Could not refresh bids: {loadError}</p><Button onClick={onRetry}>Retry</Button></div>;
 if (!cachedBids) return <div className="management-page"><h1>Bid pipeline</h1><div className="management-loading-state" role="status"><Spinner text="Loading your organization’s bids…" /><p>Preparing prices, coverage and reviews for all bids.</p></div></div>;
 const Bar=({title,items}:{title:string;items:[string,number][]})=><section className="panel management-chart"><div className="panel-header"><h2>{title}</h2><button className="text-btn" onClick={()=>setTable({...table,[title]:!table[title]})}>{table[title]?'Chart':'Table'}</button></div>{table[title]?items.map(x=><div className="management-table-row" key={x[0]}><span>{x[0]}</span><strong>{number(x[1],0)}</strong></div>):<svg viewBox="0 0 640 180" role="img" aria-label={title}>{items.map(([label,value],i)=><g key={label}><text x="0" y={28+i*30} fill="var(--text)" fontSize="12">{label}</text><rect x="145" y={16+i*30} width={Math.max(4, value/(Math.max(...items.map(x=>x[1]),1))*440)} height="16" rx="4" fill="#277350"><title>{label}: {number(value,0)}</title></rect><text x="600" y={28+i*30} textAnchor="end" fill="var(--text)" fontSize="12">{number(value,0)}</text></g>)}</svg>}</section>;
 return <div className="management-page"><div className="management-heading"><div><span className="eyebrow">MANAGEMENT</span><h1>Bid pipeline</h1><p>Select a bid to inspect its full audit trail.</p></div><Button onClick={onDuplicate}>Duplicate as variant</Button></div><div className="kpi-grid">{[['Pipeline value',money(sum(rows))],['Bids',rows.length],['Avg target margin',`${number(avg('target_margin_pct'),1)}%`],['Avg value priced',`${number(avg('pct_value_priced'),1)}%`],['Open reviews',rows.reduce((n,b)=>n+b.pending_reviews,0)]].map(x=><section className="panel kpi" key={x[0]}><span>{x[0]}</span><strong>{x[1]}</strong></section>)}</div><div className="management-charts"><Bar title="Pipeline by estimator" items={[...new Set(rows.map(b=>b.estimator))].map(e=>[e,sum(rows.filter(b=>b.estimator===e))])}/><StatusChart bids={rows} /><Bar title="Margin vs % value priced" items={rows.map(b=>[b.estimator,Number(b.target_margin_pct)+Number(b.pct_value_priced)/10])}/><Bar title="Price range per bid" items={rows.map(b=>[b.name,Number(b.offer_price||0)+Number(b.unpriced_allowance_high||0)])}/></div><section className="panel management-table"><div className="management-filters"><span className="management-filter-title">BID REGISTER</span><label className="management-filter-control"><span>Estimator</span><select value={est} onChange={e=>setEst(e.target.value)}><option value="">All estimators</option>{[...new Set(bids.map(b=>b.estimator))].map(x=><option key={x}>{x}</option>)}</select><ChevronDown size={14} /></label><label className={`management-filter-control ${status ? `status-${status}` : ''}`}><span>Status</span><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(x=><option key={x} value={x}>{statusLabels[x]}</option>)}</select><ChevronDown size={14} /></label></div><table><thead><tr>{[['estimator','Estimator'],['name','Project'],['bid_status','Status'],['offer_price','Offer'],['target_margin_pct','Margin'],['pct_value_priced','Priced'],['pending_reviews','Reviews'],['updated_at','Updated']].map(x=><th key={x[0]} onClick={()=>setSort(x[0])}>{x[1]}</th>)}<th>Audit</th><th>Open</th></tr></thead><tbody>{rows.map(b=><tr key={b.id} className={selectedBid===b.id?'selected-row':''} onClick={()=>void selectAudit(b.id)}><td>{b.estimator}</td><td>{b.name}</td><td><Badge tone="blue">{statusLabels[b.bid_status] || b.bid_status.replace('_',' ')}</Badge></td><td>{money(b.offer_price)}</td><td>{number(b.target_margin_pct,1)}%</td><td>{number(b.pct_value_priced,1)}%</td><td>{b.pending_reviews}</td><td>{date(b.updated_at)}</td><td><button className="text-btn" onClick={(e)=>{e.stopPropagation(); void selectAudit(b.id);}}><HistoryIcon size={14}/> Audit</button></td><td><button className="text-btn" onClick={(e)=>{e.stopPropagation(); onOpen(b.id);}}><ExternalLink size={14}/> Open</button></td></tr>)}</tbody></table></section>{selectedBid && <Modal open onClose={() => setSelectedBid(null)} wide title={`Audit trail · ${bids.find(b => b.id === selectedBid)?.name || 'Selected bid'}`} description={audit ? `${audit.estimator} · revision ${audit.revision} · updated ${date(audit.updated_at)}` : 'Recorded changes for the selected bid.'}>
 <div className="modal-body">
 {auditLoading && <Spinner text="Loading audit…"/>}
 {auditError && <div role="alert"><p>Could not load audit: {auditError}</p><Button onClick={() => void selectAudit(selectedBid)}>Retry</Button></div>}
 {audit && <><Badge tone="blue">{audit.history.length} changes</Badge>{audit.history.length ? <div className="management-audit-list">{audit.history.map(h => <article className="management-audit-entry" key={h.id}><div className="management-audit-meta"><strong>{label(h.entity_type)} · {historyTarget(h)}</strong><span>{date(h.timestamp)} · {h.actor} · revision {h.revision}</span></div><p>{h.reason}</p><HistoryChanges decision={h}/></article>)}</div> : <p>No changes have been recorded for this bid.</p>}</>}
 </div>
 </Modal>}{rows.length<2&&<div className="empty-state"><h2>Create variants to compare estimators</h2><Button onClick={onDuplicate}>Duplicate</Button></div>}</div>;
}
