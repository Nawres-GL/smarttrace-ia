import React, {useEffect,useState} from 'react';
import './traceability.css';
const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
const labels={RECEPTION_SEMENCES:'Réception des semences',SEMIS:'Semis',GERMINATION:'Germination',TRANSFERT:'Transfert',PERTE:'Pertes',CONTROLE_QUALITE:'Contrôle qualité',LIVRAISON:'Livraison',TRAITEMENT:'Traitement',GREFFAGE:'Greffage'};
async function get(token,path,signal){
 const r=await fetch(`${API}${path}`,{headers:{Authorization:`Bearer ${token}`},signal});
 const body=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:`Erreur HTTP ${r.status}`);
 return body;
}
export default function TraceabilityPage({token,onOpenLot}){
 const [lots,setLots]=useState([]),[search,setSearch]=useState(''),[lotId,setLotId]=useState('');
 const [detail,setDetail]=useState(null),[integrity,setIntegrity]=useState(null),[qr,setQr]=useState(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0),[checking,setChecking]=useState(false);
 useEffect(()=>{if(!token)return;const ctrl=new AbortController();setBusy(true);setError('');
 get(token,'/api/operations/lots?limit=500',ctrl.signal).then(d=>setLots(Array.isArray(d)?d:[]))
 .catch(e=>{if(!ctrl.signal.aborted)setError(e.message)}).finally(()=>{if(!ctrl.signal.aborted)setBusy(false)});
 return ()=>ctrl.abort();},[token,refresh]);
 useEffect(()=>{setDetail(null);setIntegrity(null);setQr(null);if(!lotId)return;
 const ctrl=new AbortController();setBusy(true);setError('');
 Promise.all([get(token,`/api/operations/lots/${encodeURIComponent(lotId)}`,ctrl.signal),get(token,`/api/operations/lots/${encodeURIComponent(lotId)}/qr`,ctrl.signal)])
 .then(([d,q])=>{setDetail(d);setQr(q)}).catch(e=>{if(!ctrl.signal.aborted)setError(e.message)})
 .finally(()=>{if(!ctrl.signal.aborted)setBusy(false)});return ()=>ctrl.abort();},[token,lotId]);
 const matching=lots.filter(l=>[l.code,l.species,l.variety,l.article,l.site_code].some(s=>String(s||'').toLowerCase().includes(search.toLowerCase())));
 async function check(){setChecking(true);setError('');try{setIntegrity(await get(token,`/api/operations/lots/${encodeURIComponent(lotId)}/integrity`));}catch(e){setError(e.message)}finally{setChecking(false)}}
 async function download(fmt){try{setError('');const r=await fetch(`${API}/api/investigations/lots/${encodeURIComponent(lotId)}/export?format=${fmt}`,{headers:{Authorization:`Bearer ${token}`}});
 if(!r.ok){const x=await r.json().catch(()=>({}));throw Error(x.detail||`Export impossible (HTTP ${r.status})`)}
 const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`fiche-enquete-${detail.lot.code}.${fmt}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)
 }catch(e){setError(e.message)}}
 return <section className="trace-page">
 <header className="trace-header"><div><span className="trace-eyebrow">SUIVI DES OPÉRATIONS · MONGODB</span><h1>Traçabilité des lots</h1><p>Consultez les étapes agricoles enregistrées, le QR code et les dossiers. Aucun identifiant technique n'est demandé.</p></div><button onClick={()=>setRefresh(x=>x+1)} disabled={busy}>Actualiser</button></header>
 {error&&<p className="trace-error" role="alert">{error}</p>}
 <div className="trace-panel"><h2>Rechercher un lot opérationnel</h2><label>Code, variété ou espèce<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Ex. RP-S01, TOMATE…"/></label>
 <label>Lot de production<select value={lotId} onChange={e=>setLotId(e.target.value)}><option value="">Choisir un lot ({matching.length} résultat(s))</option>{matching.map(l=><option key={l.id} value={l.id}>{l.code} · {l.variety||l.article||'Variété à renseigner'} · {l.site_code}</option>)}</select></label>
 {busy&&<p role="status">Chargement…</p>}
 {detail&&<><div className="trace-lot-head"><div><h3>{detail.lot.code}</h3><p>{detail.lot.variety||'Variété non renseignée'} · Site {detail.lot.site_code} · {detail.lot.status?.replaceAll('_',' ')}</p></div><button onClick={()=>onOpenLot(detail.lot.id)}>Ouvrir le dossier complet</button></div>
 <div className="trace-actions"><button onClick={check} disabled={checking}>{checking?'Vérification…':'Contrôler les empreintes locales'}</button><button onClick={()=>download('pdf')}>Fiche PDF</button><button onClick={()=>download('docx')}>Fiche Word</button></div>
 {integrity&&<div className={'trace-integrity '+(integrity.local_consistency?'trace-valid':'trace-invalid')} role="status"><strong>{integrity.local_consistency?'Cohérence locale : correcte':'Anomalie de cohérence détectée'}</strong><p>{integrity.checked_events} événements examinés. {integrity.note}{integrity.truncated?' Résultat limité à 500 événements.':''}</p></div>}
 <h3>Chronologie des opérations ({detail.events?.length||0})</h3><div className="trace-timeline">{(detail.events||[]).map(e=><article key={e.id} className="trace-event"><b>{labels[e.event_type]||e.event_type}</b><small>{e.occurred_at?new Date(e.occurred_at).toLocaleString('fr-FR'):'Date inconnue'}</small><div className="trace-event-details">{Object.entries(e.details||{}).slice(0,7).map(([k,v])=><span key={k}>{k.replaceAll('_',' ')} : {String(v??'—')}</span>)}</div></article>)}{!detail.events?.length&&<p>Aucun événement opérationnel enregistré.</p>}</div>
 {qr&&<div className="trace-qr"><img src={qr.image_data_url} alt={`QR code du lot ${detail.lot.code}`}/><div><b>QR code du lot</b><p>Accès au dossier après authentification.</p><a href={qr.image_data_url} download={`QR-${detail.lot.code}.png`}>Enregistrer le QR code</a></div></div>}
 </>}
 </div><p className="trace-foot">Les anciens et nouveaux lots sont réunis dans « Registre des lots ». Le contrôle SHA-256 n'est pas une certification indépendante.</p></section>
}
