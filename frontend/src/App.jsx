import React, { useEffect, useState } from 'react';
import './style.css';
import OperationalWorkspace from './OperationalWorkspace.jsx';
import AssistantNLP from './AssistantNLP.jsx';
import RAGAssistant from './RAGAssistant.jsx';
import LotHistoryFilters from './LotHistoryFilters.jsx';
import TraceabilityPage from './TraceabilityPage.jsx';
import InvestigationCases from './InvestigationCases.jsx';
import InsightsDashboard from './InsightsDashboard.jsx';
import SourceImports from './SourceImports.jsx';
import UnifiedRegistry from './UnifiedRegistry.jsx';
import HistoricalTimeline from './HistoricalTimeline.jsx';
import './operations.css';
import './ui-polish.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const nf = new Intl.NumberFormat('fr-FR');
const fmt = n => nf.format(Number(n || 0));
const shown = x => (x === null || x === undefined || x === '' ? '—' : String(x));

const routes = [
  { key:'dashboard', icon:'grid', name:'Vue générale' },
  { key:'lots', icon:'layers', name:'Registre des lots' },
  { key:'production', icon:'leaf', name:'Production active' },
  { key:'quality', icon:'shield', name:'Contrôle qualité' },
  { key:'delivery', icon:'truck', name:'Préparation & livraison' },
  { key:'sources', icon:'database', name:'Données sources' },
  { key:'insights', icon:'grid', name:'Statistiques & insights' },
  { key:'architecture', icon:'shield', name:'Traçabilité des lots' },
  { key:'investigations', icon:'alert', name:'Enquêtes & réclamations' },
  { key:'assistant', icon:'spark', name:'Assistant NLP' },
  { key:'rag', icon:'search', name:'Assistant RAG' },
];

function Icon({name, size=19, strokeWidth=1.8}) {
  const paths = {
    grid:<><rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/></>,
    layers:<><path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/></>,
    database:<><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/></>,
    shield:<><path d="m12 22 1.3-.5C18.5 19.4 21 15.4 21 10V5l-9-3-9 3v5c0 5.4 2.5 9.4 7.7 11.5L12 22Z"/><path d="m9 12 2 2 4-4"/></>,
    search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    arrow:<><path d="M4 12h16m-7-7 7 7-7 7"/></>,
    box:<><path d="m12 2 9 5-9 5-9-5 9-5Zm-9 5v10l9 5 9-5V7M12 12v10"/></>,
    truck:<><path d="M2 5h12v12H2zM14 9h4l4 4v4h-8z"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></>,
    link:<><path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"/></>,
    alert:<><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 4h.01"/></>,
    calendar:<><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M7 2v4m10-4v4M3 9h18"/></>,
    close:<><path d="m5 5 14 14M19 5 5 19"/></>,
    chevron:<><path d="m9 18 6-6-6-6"/></>,
    leaf:<><path d="M20 4c-12 0-17 5-17 12a5 5 0 0 0 5 5c7 0 12-5 12-17Z"/><path d="M3 21c5-6 9-10 15-14"/></>,
    spark:<><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z"/></>,
    circle:<><circle cx="12" cy="12" r="9"/><path d="M12 8v5m0 3h.01"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.circle}</svg>;
}

function PlantScene() {
  const [hovered, setHovered] = useState(false);
  return <div className={'scene '+(hovered?'scene-hover':'')} onPointerEnter={()=>setHovered(true)} onPointerLeave={()=>setHovered(false)} aria-hidden="true">
    <span className="scene-glow"/>
    <div className="tray-space">
      <div className="tray-cube">
        <div className="tray-top"><div className="plant-grid">{Array.from({length:12},(_,i)=><div className="plant-cell" key={i}><span className="soil"/><span className="stem"><i className="leaf-left"/><i className="leaf-right"/></span></div>)}</div></div>
        <div className="tray-front"/><div className="tray-side"/>
      </div>
    </div>
    <div className="scene-callout callout-top"><span className="callout-dot"/> LOTS <span className="callout-success">• HISTORIQUE</span></div>
    <div className="scene-callout callout-bottom"><Icon name="shield" size={14}/> Traçabilité intelligente</div>
    <span className="orbit orbit-a"/><span className="orbit orbit-b"/>
  </div>;
}

function StatusPill({status}) {
  const isLink = status==='LOT_LIE', uncertain=status==='PLUSIEURS_REFERENCES';
  const value = isLink?'Correspondance Excel':uncertain?'Références multiples':status==='PRODUCTION_SEULE'?'Production seule':status==='GREFFE_SEULE'?'Greffage seul':status==='GREFFE_LIVRAISON'?'Greffage & livraisons':'Livraison seule';
  return <span className={'pill '+(isLink?'pill-muted':uncertain?'pill-amber':'pill-muted')}><i/>{value}</span>;
}

function Stat({icon, label, value, sub, tone}) {
  return <div className="stat-card"><div className={'stat-icon '+tone}><Icon name={icon} size={22}/></div><div className="stat-body"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div></div>;
}

function SectionHead({eyebrow,title,children}) {
  return <div className="section-head"><div><span className="section-eyebrow">{eyebrow}</span><h2>{title}</h2></div>{children}</div>;
}

async function exportOperationalLot(token, lotId, code, format, setError) {
  setError('');
  try {
    const response=await fetch(`${API}/api/investigations/lots/${encodeURIComponent(lotId)}/export?format=${format}`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok){const x=await response.json().catch(()=>({}));throw Error(typeof x.detail==='string'?x.detail:`Export impossible (HTTP ${response.status}).`);}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');
    a.href=url;a.download=`fiche-enquete-${String(code||'lot').replace(/[^A-Za-z0-9_-]/g,'')}.${format}`;
    document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
  }catch(e){setError(e.message);}
}

async function exportHistoricalLot(token, code, format, setBusy, setError) {
  setBusy(format); setError('');
  try {
    const response = await fetch(`${API}/api/investigations/historique/lots/${encodeURIComponent(code)}/export?format=${format}`, {
      headers: {Authorization: `Bearer ${token}`},
    });
    if (!response.ok) {
      const body = await response.json().catch(()=>({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `Échec de l’export (HTTP ${response.status}).`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `fiche-enquete-historique-${code}.${format}`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 2000);
  } catch (err) {setError(err.message || 'Export impossible.');}
  finally {setBusy('');}
}

function DetailModal({detail, close, token}) {
  const [exportBusy, setExportBusy] = useState('');
  const [exportError, setExportError] = useState('');
  if (!detail) return null;
  const {summary,production,deliveries,grafting=[],warnings} = detail;
  return <div className="modal-backdrop" onMouseDown={close}><aside className="lot-drawer" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label={'Dossier du lot '+summary.lot_code}>
    <header className="drawer-top"><div><span className="section-eyebrow">DOSSIER DE TRAÇABILITÉ</span><h2>Lot {summary.lot_code}</h2><StatusPill status={summary.status}/></div><button className="round-btn" aria-label="Fermer" onClick={close}><Icon name="close"/></button></header>
    <div className="drawer-scroll">
      <HistoricalTimeline production={production} grafting={grafting} deliveries={deliveries}/>
      <div className="historical-export-actions" style={{marginBottom:16,padding:15,border:'1px solid #9ccdb2',borderRadius:12}}>
        <b>Fiche d’enquête externe — lot historique {summary.lot_code}</b>
        <p style={{margin:'6px 0 10px'}}>Brouillon prérempli depuis les lignes Excel disponibles. Les observations terrain et avis de l’ingénieur restent à compléter. Archives Excel : informations à contrôler.</p>
        <div style={{display:'flex',gap:10,flexWrap:'wrap'}}>
          <button type="button" disabled={!!exportBusy} onClick={()=>exportHistoricalLot(token,summary.lot_code,'pdf',setExportBusy,setExportError)}>{exportBusy==='pdf'?'Export…':'Exporter la fiche PDF'}</button>
          <button type="button" disabled={!!exportBusy} onClick={()=>exportHistoricalLot(token,summary.lot_code,'docx',setExportBusy,setExportError)}>{exportBusy==='docx'?'Export…':'Exporter la fiche Word'}</button>
        </div>
        {exportError&&<p role="alert" style={{color:'#ad3535'}}>{exportError}</p>}
      </div>
      <div className="source-note"><Icon name="circle" size={17}/><span>Données historiques provenant des fichiers Excel. Ces informations proviennent des archives Excel et sont à vérifier avant toute décision opérationnelle.</span></div>
      {warnings.length>0 && <div className="warning-stack">{warnings.map((w,i)=><div className="warning" key={i}><Icon name="alert" size={16}/>{w}</div>)}</div>}
      <h3>Informations de production</h3>
      {production.length?production.map((p,i)=><div className="production-record" key={i}><div className="record-title"><Icon name="leaf" size={18}/><b>{shown(p.lot_ref)}</b><span>Ligne Excel {p.source_row}</span></div><div className="detail-grid">
        <div><span>Article</span><b>{shown(p.article)}</b></div><div><span>Variété</span><b>{shown(p.variety || p.species)}</b></div>
        <div><span>Lot semences</span><b>{shown(p.seed_lot_ref)}</b></div><div><span>Semis</span><b>{shown(p.sowing_date)}</b></div>
        <div><span>Quantité semée</span><b>{shown(p.seeds_sown)}</b></div><div><span>Plants nets</span><b>{shown(p.plants_net)}</b></div>
        <div><span>Dépôt</span><b>{shown(p.production_site_or_depot)}</b></div><div><span>Livré (résumé)</span><b>{shown(p.plants_delivered_summary)}</b></div>
      </div></div>):<p className="zero-state">Aucune ligne de production pour ce numéro de lot.</p>}
      <h3>Production greffée <em>{grafting.length} ligne(s)</em></h3>
      {grafting.length ? grafting.map((g,i)=><div className="production-record graft-record" key={i}>
        <div className="record-title"><Icon name="leaf" size={18}/><b>{shown(g.lot_ref)}</b><span>Ligne Excel {g.source_row}</span></div>
        <div className="detail-grid">
          <div><span>Article greffé</span><b>{shown(g.article)}</b></div>
          <div><span>Variété</span><b>{shown(g.variety)}</b></div>
          <div><span>Serre</span><b>{shown(g.greenhouse)}</b></div>
          <div><span>Nature</span><b>{shown(g.grafting_type)}</b></div>
          <div><span>Taux de greffage</span><b>{g.grafting_rate_pct==null?'—':Number(g.grafting_rate_pct).toFixed(1)+' %'}</b></div>
          <div><span>Perte de greffage</span><b>{g.grafting_loss_pct==null?'—':Number(g.grafting_loss_pct).toFixed(1)+' %'}</b></div>
          <div><span>Quantité nette</span><b>{shown(g.plants_net)} plants</b></div>
          <div><span>Validé le (source)</span><b>{shown(g.validated_on)}</b></div>
        </div><p className="source-caption">Historique Excel · « DS. Réel » n’est pas interprété automatiquement comme date de greffage.</p>
      </div>):<p className="zero-state">Aucune donnée de greffage pour ce numéro de lot.</p>}
      <h3>Livraisons et retours <em>{deliveries.length} ligne(s)</em></h3>
      {deliveries.length?<div className="delivery-stack">{deliveries.slice(0,100).map((d,i)=><div className="delivery-item" key={i}><div className="deliver-top"><b>{shown(d.client)}</b><span>{shown(d.document_date)}</span></div><div className="delivery-info"><span><Icon name="truck" size={14}/> Bon n° {shown(d.delivery_note_number)}</span><span>{shown(d.tray_quantity)} plateaux</span><span>{shown(d.item_quantity)} {shown(d.unit)}</span></div><div className="delivery-bottom"><span>Type : {shown(d.type)} · Ligne Excel {d.source_row}</span>{d.article_matches_production===false&&<span className="mismatch">Article à vérifier</span>}</div>{d.manual_review&&<p className="source-caption" style={{marginTop:8,padding:'8px 10px',borderRadius:8,background:'#eaf5ed',color:'#215a39'}}><strong>{d.manual_review.decision==='CONFIRM_LINK'?'Rapprochement confirmé par revue humaine':'Rapprochement écarté après revue'}</strong> · {d.manual_review.reason}. Les archives originales restent inchangées.</p>}</div>)}</div>:<p className="zero-state">Aucune livraison associée dans le fichier fourni.</p>}
      {deliveries.length>100&&<div className="source-note">Seules les 100 premières lignes sont affichées dans cette vue.</div>}
    </div>
  </aside></div>;
}

function Login({onLogin}){
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[pending,setPending]=useState(false),[error,setError]=useState('');
  async function login(e){e.preventDefault();setPending(true);setError('');try{const response=await fetch(`${API}/api/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});const data=await response.json().catch(()=>({}));if(!response.ok){const fields=(data.errors||[]).map(x=>`${x.field}: ${x.message}`).join(' · ');throw new Error(fields|| (typeof data.detail==='string'?data.detail:'Connexion impossible.'));}onLogin(data);}catch(e){setError(e.message);}finally{setPending(false);}}
  return <div className="login-screen"><section className="login-visual"><div className="login-symbol">✦ Royal Plants <span>SMARTTRACE SYSTEM</span></div><div className="login-art" aria-hidden="true">🌱</div><div><h1>Une production claire. Une traçabilité fiable.</h1><p>Suivez chaque lot, contrôlez les quantités et reliez les opérations agricoles à leurs livraisons.</p></div></section><section className="login-form-wrap"><div className="login-card"><span className="login-eyebrow">ACCÈS PROFESSIONNEL</span><h2>Bienvenue.</h2><p>Connectez-vous à votre espace de pilotage Royal Plants.</p><form onSubmit={login}><label>Adresse e-mail<input type="email" value={email} autoComplete="username" onChange={e=>setEmail(e.target.value)} required placeholder="prenom@royalplants.tn"/></label><label>Mot de passe<input type="password" value={password} autoComplete="current-password" onChange={e=>setPassword(e.target.value)} required placeholder="Votre mot de passe"/></label>{error&&<div role="alert" className="login-message">{error}</div>}<button disabled={pending}>{pending?'Connexion…':'Accéder à SmartTrace →'}</button></form><p className="login-note">Prototype interne · accès réservé · les documents Excel originaux sont conservés sans modification.</p></div></section></div>;
}

export default function App(){
  const [session,setSession]=useState(null);
  const token=session?.access_token;
  const [deepLink,setDeepLink]=useState(()=>new URLSearchParams(window.location.search).get('lot'));
  const [historyQrCode,setHistoryQrCode]=useState(()=>{const p=new URLSearchParams(window.location.search).get('trace')||'';return /^historical:\d{5}$/.test(p)?p.slice(11):'';});
  function signOut(){setSession(null);setDetail(null);setOverview(null);setLots([]);setNlpDraft(null);setError('');}

  const [page,setPage] = useState('dashboard');
  const [menuOpen,setMenuOpen] = useState(false);
  useEffect(()=>{setMenuOpen(false);},[page]);
  useEffect(()=>{const onKey=e=>{if(e.key==='Escape')setMenuOpen(false)};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey)},[]);
  const [nlpDraft,setNlpDraft] = useState(null);
  const [caseLotId,setCaseLotId] = useState('');
  function startInvestigation(lotId){setCaseLotId(lotId);setPage('investigations')}

  // Interpretations stay drafts: only the existing operation form may submit.
  function applyNlpDraft(draft) {
    if (!draft?.ready_for_review || !draft.action || draft.review_flags?.length ||
        !draft.allowed_actions?.includes(draft.action)) return;
    setNlpDraft({ ...draft, draft_nonce: Date.now() });
    const target = draft.action === 'quality' ? 'quality'
      : ['preparation','delivery','return'].includes(draft.action) ? 'delivery'
      : 'production';
    setPage(target);
  }

  const [dataRevision,setDataRevision]=useState(0);
  const [overview,setOverview]=useState(null),[lots,setLots]=useState([]),[total,setTotal]=useState(0);
  const [search,setSearch]=useState(''),[offset,setOffset]=useState(0);
  const [historyFilters,setHistoryFilters]=useState({campaign:'', species:'', article:''});
  const [detail,setDetail]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [detailLoading,setDetailLoading]=useState(false);
  const [operationalLots,setOperationalLots]=useState([]);
  const [operationalLoading,setOperationalLoading]=useState(false);
  const [operationalError,setOperationalError]=useState('');
  const [operationalSearch,setOperationalSearch]=useState('');
  const [operationalRefresh,setOperationalRefresh]=useState(0);
  useEffect(()=>{
    if(!token||session?.user?.role!=='admin'||page!=='lots')return;
    const ctrl=new AbortController();setOperationalLoading(true);setOperationalError('');
    fetch(`${API}/api/operations/lots?limit=500`,{headers:{Authorization:`Bearer ${token}`},signal:ctrl.signal})
      .then(async response=>{const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:`Erreur HTTP ${response.status}`);return body;})
      .then(body=>{if(!ctrl.signal.aborted)setOperationalLots(Array.isArray(body)?body:[]);})
      .catch(e=>{if(!ctrl.signal.aborted)setOperationalError(e.message);})
      .finally(()=>{if(!ctrl.signal.aborted)setOperationalLoading(false);});
    return ()=>ctrl.abort();
  },[token,page,operationalRefresh]);
  const matchingOperational=operationalLots.filter(l=>[l.code,l.species,l.variety,l.article,l.campaign,l.site_code].some(x=>String(x||'').toLowerCase().includes(operationalSearch.toLowerCase())));
  function openOperationalLot(lotId){setDeepLink(lotId);setPage('production');}


  async function api(path){const r=await fetch(`${API}${path}`,{headers:{Authorization:`Bearer ${token}`}});const json=await r.json().catch(()=>({}));if(!r.ok)throw new Error(json.detail||'Impossible de charger les données');return json;}
  const historyParams = () => new URLSearchParams({
    campaign:historyFilters.campaign, species:historyFilters.species, article:historyFilters.article,
  }).toString();
  useEffect(()=>{
    if(!token||session.user.role!=='admin')return;
    let alive=true;
    api(`/api/historique/overview?${historyParams()}`)
      .then(x=>{if(alive)setOverview(x);}).catch(e=>{if(alive)setError(e.message);});
    return ()=>{alive=false;};
  },[token,historyFilters,dataRevision]);
  useEffect(()=>{
    if(!token||session.user.role!=='admin')return;
    let alive=true;
    const t=setTimeout(()=>{
      const params=new URLSearchParams({search,limit:'24',offset:String(offset),
        campaign:historyFilters.campaign,species:historyFilters.species,article:historyFilters.article});
      api(`/api/historique/lots?${params.toString()}`).then(d=>{
        if(alive){setLots(d.items);setTotal(d.total);setLoading(false);}
      }).catch(e=>{if(alive){setError(e.message);setLoading(false);}});
    },180);
    return ()=>{alive=false;clearTimeout(t);};
  },[search,offset,token,historyFilters,dataRevision]);
  async function openLot(code){setDetailLoading(true);try{setError('');setDetail(await api('/api/historique/lots/'+encodeURIComponent(code)));}catch(e){setError(e.message);}finally{setDetailLoading(false);}}
  useEffect(()=>{if(!token||!historyQrCode)return; if(session?.user?.role!=='admin'){setError('Accès aux archives historiques réservé aux administrateurs.');setHistoryQrCode('');return;}setPage('lots');openLot(historyQrCode);setHistoryQrCode('');},[token,historyQrCode]);
  const setQuery=s=>{setSearch(s);setOffset(0);};
  function updateHistoryFilter(field, nextValue) {
    setHistoryFilters(prev=>({
      ...prev, [field]:nextValue,
      ...(field==='campaign'?{species:'',article:''}:{}),
      ...(field==='species'?{article:''}:{}),
    }));
    setOffset(0);
  }
  function resetHistoryFilters(){setHistoryFilters({campaign:'',species:'',article:''});setSearch('');setOffset(0);}
  if(!session)return <Login onLogin={data=>{setSession(data);setPage(deepLink?'production':(historyQrCode?'lots':(data.user.role!=='admin'?'production':'dashboard')));}}/>;
  return <div className="shell">
    {menuOpen&&<button type="button" className="mobile-nav-backdrop" onClick={()=>setMenuOpen(false)} aria-label="Fermer la navigation"/>}
    <aside className={'sidebar '+(menuOpen?'sidebar-open':'')} id="smarttrace-sidebar"><div className="brand-row"><div className="brand-mark"><Icon name="leaf" size={23}/></div><div><strong>Royal Plants</strong><small>SMARTTRACE SYSTEM</small></div></div>
      <button className="mobile-close" onClick={()=>setMenuOpen(false)} aria-label="Fermer le menu"><Icon name="close"/> Fermer</button><div className="workspace-label">ESPACE DE TRAVAIL</div><nav className="side-nav" aria-label="Navigation principale">{routes.filter(r=>r.key==='rag'||session.user.role==='admin'||({production:['production','assistant','architecture','investigations'],qualite:['production','quality','assistant','architecture','investigations'],logistique:['production','delivery','assistant','architecture','investigations'],lecture:['production','architecture','investigations']}[session.user.role]||[]).includes(r.key)).map(r=><button className={'nav-item '+(page===r.key?'active':'')} key={r.key} onClick={()=>setPage(r.key)}><Icon name={r.icon}/><span>{r.name}</span>{page===r.key&&<span className="nav-marker"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="help-box"><div className="help-icon"><Icon name="shield"/></div><strong>Traçabilité de confiance</strong><p>Une source de vérité pour chaque lot, de la semence au client.</p></div><div className="sidebar-footer"><span className="user-dot">RP</span><div><b>{session.user.name}</b><small>{session.user.role} · pilote</small></div></div><button className="signout-btn" onClick={signOut}>Se déconnecter</button></div>
    </aside>
    <div className="main-zone"><div className="topbar"><button className="mobile-menu-toggle" type="button" aria-label="Ouvrir le menu" aria-controls="smarttrace-sidebar" aria-expanded={menuOpen} onClick={()=>setMenuOpen(v=>!v)}><span>☰</span> Menu</button><div className="breadcrumb">Espace de travail <Icon name="chevron" size={14}/> <strong>{routes.find(x=>x.key===page)?.name}</strong></div><div className="top-actions"><span className="mode-dot"/> <span className="readonly-status">Atlas + Excel non modifié</span><div className="avatar">RP</div></div></div>
      <main className="content">
        {['production','quality','delivery'].includes(page)&&<OperationalWorkspace token={token} mode={page} userRole={session.user.role} deepLink={deepLink} onDeepLinkHandled={()=>setDeepLink(null)} nlpDraft={nlpDraft} onNlpDraftConsumed={()=>setNlpDraft(null)}/>}
        {page==='assistant'&&<AssistantNLP token={token} onApply={applyNlpDraft}/>}
        {page==='rag'&&<RAGAssistant token={token}/>}
        {page==='investigations'&&<InvestigationCases token={token} userRole={session.user.role} initialLotId={caseLotId} onOpenLot={openOperationalLot}/>}
        {page==='dashboard'&&<><section className="hero"><div className="hero-copy"><div className="hero-kicker"><span className="kicker-line"/> PLATEFORME DE TRAÇABILITÉ AGRICOLE</div><h1>Chaque lot a une histoire.<br/><span>Retrouvez-la en un instant.</span></h1><p>Reliez les données de production et de livraison, consultez l’historique complet et préparez la traçabilité de demain.</p><button className="primary-btn" onClick={()=>{setPage('lots');document.getElementById('lotsearch')?.focus();}}>Explorer les lots <Icon name="arrow" size={17}/></button><div className="hero-foot"><span className="pulse"/> Données réelles · Connexion par n° de lot</div></div><PlantScene/></section>
          <div className="stats-grid"><Stat icon="box" label="Lignes de production" value={overview?fmt(overview.production_rows):'—'} sub={historyFilters.campaign||historyFilters.species||historyFilters.article?"Excel historique · vue filtrée":"Fichier Production Excel"} tone="green"/><Stat icon="truck" label="Lignes de livraison" value={overview?fmt(overview.delivery_rows):'—'} sub={historyFilters.campaign||historyFilters.species||historyFilters.article?"Excel historique · vue filtrée":"Fichier Livraison Excel"} tone="blue"/><Stat icon="link" label="Lots reliés" value={overview?fmt(overview.linked_lots):'—'} sub="Identifiant à 5 chiffres" tone="purple"/><Stat icon="layers" label="Lots de production" value={overview?fmt(overview.production_lots):'—'} sub="Références numériques uniques" tone="orange"/><Stat icon="leaf" label="Lignes de greffage" value={overview?fmt(overview.grafting_rows):'—'} sub="Troisième fichier Excel, lié par LOT" tone="purple"/></div>
          <section className="info-strip"><div className="info-strip-icon"><Icon name="link"/></div><div><b>Une seule règle de rapprochement</b><p><code>LOT : RO-XXXXX/25</code> <Icon name="arrow" size={15}/> <code>XXXXX</code> <Icon name="arrow" size={15}/> <code>N° Lot : XXXXX</code></p></div><span className="source-chip">Aucun fichier modifié</span></section></>}
        {page==='lots'&&<UnifiedRegistry token={token} onOpenHistorical={openLot} onOpenOperational={openOperationalLot}/>}
        {page==='dashboard'&&<section className="registry"><SectionHead eyebrow="RECHERCHE INTELLIGENTE" title={page==='lots'?'Archives Excel · lots historiques':'Lots de production & livraisons'}><span className="count-label">{fmt(total)} identifiant(s)</span></SectionHead><div className="toolbar"><div className="search-input"><Icon name="search" size={19}/><input id="lotsearch" aria-label="Rechercher un lot" value={search} onChange={e=>setQuery(e.target.value)} placeholder="Rechercher n° lot, article ou variété..."/></div><button className="filter-btn" onClick={resetHistoryFilters}><Icon name="search" size={17}/> Tout afficher</button></div>
          <LotHistoryFilters token={token} value={historyFilters} onChange={updateHistoryFilter} onReset={resetHistoryFilters}/>
          {error&&<div className="error-box"><Icon name="alert"/>{error}<button onClick={()=>setError('')} aria-label="Masquer l'erreur"><Icon name="close" size={14}/></button></div>}
          <div className="registry-table"><table><thead><tr><th>NUMÉRO DE LOT</th><th>ARTICLE / VARIÉTÉ</th><th>PRODUCTION</th><th>GREFFAGE</th><th>LIVRAISONS</th><th>ÉTAT</th><th/></tr></thead><tbody>{lots.map(l=><tr key={l.lot_code} onClick={()=>openLot(l.lot_code)} tabIndex="0" onKeyDown={e=>{if(e.key==='Enter')openLot(l.lot_code);}}><td><div className="lot-code"><span className="mini-box"><Icon name="box" size={15}/></span><strong>{l.lot_code}</strong></div><small className="lot-ref">{l.lot_refs[0]||'N° Lot : '+l.lot_code}</small></td><td><b>{shown(l.articles[0])}</b><small>{shown(l.varieties[0])}</small></td><td><b>{fmt(l.production_rows)} ligne(s)</b></td><td><b>{fmt(l.grafting_rows||0)} ligne(s)</b></td><td><b>{fmt(l.delivery_rows)} ligne(s)</b></td><td><StatusPill status={l.status}/></td><td><button type="button" className="filter-btn" title="Exporter une fiche d’enquête externe PDF (brouillon historique)" onClick={e=>{e.stopPropagation();exportHistoricalLot(token,l.lot_code,'pdf',()=>{},setError);}}>Fiche PDF</button></td></tr>)}</tbody></table>
            {!lots.length&&<div className="empty-table"><Icon name="search" size={28}/><b>{loading?'Chargement en cours…':'Aucun lot trouvé'}</b><p>Vérifiez les fichiers Excel ou modifiez votre recherche.</p></div>}</div>
          <div className="table-footer"><span>Affichage {total===0?0:offset+1}–{Math.min(offset+24,total)} sur {fmt(total)} lots</span><div className="page-buttons"><button disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-24))}>Précédent</button><button disabled={offset+24>=total} onClick={()=>setOffset(x=>x+24)}>Suivant <Icon name="arrow" size={15}/></button></div></div>
        </section>}
        {page==='insights'&&<InsightsDashboard token={token} revision={dataRevision}/>}
        {page==='sources'&&<><section className="page-heading"><span className="section-eyebrow">INTÉGRATION · DONNÉES</span><h1>Données historiques & imports Atlas</h1><p>Importer les archives Excel dans MongoDB sans modifier les fichiers originaux, puis relier les lots dans le registre unifié.</p></section><div className="source-grid"><div className="source-card"><div className="source-icon green"><Icon name="leaf" size={28}/></div><h3>Production_franc_valid-3.xlsx</h3><p>LOT, variété, semis, germination, quantités de plants, pertes et conditions.</p><div className="source-count">{fmt(overview?.production_rows)} <small>lignes importables</small></div></div><div className="source-card"><div className="source-icon blue"><Icon name="truck" size={28}/></div><h3>LivraisonC25_Clean-walid.xlsx</h3><p>N° Lot, client, bon de livraison, date document, article, plateaux, quantités.</p><div className="source-count">{fmt(overview?.delivery_rows)} <small>lignes importables</small></div></div><div className="source-card"><div className="source-icon green"><Icon name="leaf" size={28}/></div><h3>Production_Greffee_Final_corrected-1.xlsx</h3><p>LOT / Lot_Production, serre, variété, taux de greffage, pertes et quantités.</p><div className="source-count">{fmt(overview?.grafting_rows)} <small>lignes de greffage</small></div></div></div><div className="source-note source-page-notice"><Icon name="shield"/>Les fichiers originaux sont toujours conservés tels quels. Le rapprochement est un calcul de lecture, et non une modification Excel.</div><SourceImports token={token} onImported={()=>setDataRevision(n=>n+1)}/></>}
        {page==='architecture'&&<TraceabilityPage token={token} onOpenLot={openOperationalLot}/>}
        <footer className="app-footer"><span>© Royal Plants · SmartTrace</span><span>Prototype interne · historique opérationnel dans MongoDB</span></footer>
      </main></div>
      {detailLoading&&<div className="loading-pop">Ouverture du dossier…</div>}
      {detail&&<DetailModal detail={detail} token={token} close={()=>setDetail(null)}/>}
  </div>;
}
