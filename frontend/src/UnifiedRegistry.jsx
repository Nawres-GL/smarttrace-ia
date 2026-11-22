import React,{useEffect,useState} from 'react';
import './unified-registry.css';
const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';

export default function UnifiedRegistry({token,onOpenHistorical,onOpenOperational}){
 const [search,setSearch]=useState(''),[kind,setKind]=useState('all'),[offset,setOffset]=useState(0);
 const [result,setResult]=useState({total:0,items:[]});
 const [error,setError]=useState(''),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0);
 const [qr,setQr]=useState(null),[qrBusy,setQrBusy]=useState(false),[repairing,setRepairing]=useState(false);
 const get=async(path,options={})=>{
   const r=await fetch(`${API}${path}`,{...options,headers:{Authorization:`Bearer ${token}`,...options.headers}});
   const data=await r.json().catch(()=>({}));
   if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Erreur ${r.status}`);
   return data;
 };
 useEffect(()=>{
   const c=new AbortController(); const timer=setTimeout(()=>{
     setLoading(true);setError('');
     const q=new URLSearchParams({kind,search,offset:String(offset),limit:'30'});
     get('/api/registry/lots?'+q,{signal:c.signal}).then(x=>{if(!c.signal.aborted)setResult(x)})
      .catch(e=>{if(!c.signal.aborted)setError(e.message)})
      .finally(()=>{if(!c.signal.aborted)setLoading(false)});
   },150);
   return ()=>{clearTimeout(timer);c.abort()};
 },[token,search,kind,offset,revision]);
 const pickKind=v=>{setKind(v);setOffset(0)};
 const showQr=async(item)=>{
   setError('');setQrBusy(true);
   try{
     const path=item.kind==='historical'
      ? `/api/registry/historical/${encodeURIComponent(item.code)}/qr`
      : `/api/operations/lots/${encodeURIComponent(item.operationalLotId)}/qr`;
     setQr({...await get(path),item});
   }catch(e){setError(e.message)}finally{setQrBusy(false)}
 };
 const rebuild=async()=>{
   setRepairing(true);setError('');
   try{
     const out=await get('/api/registry/rebuild',{method:'POST'});
     setRevision(x=>x+1);setOffset(0);
     window.alert(`Registre actualisé : ${out.historical_lots} historiques et ${out.operational_lots} opérationnels.`);
   }catch(e){setError(e.message)}finally{setRepairing(false)}
 };
 return <section className="ur-section">
   <header className="ur-header"><div><span className="ur-kicker">SOURCE UNIQUE DE CONSULTATION</span><h1>Registre unifié des lots</h1>
    <p>Retrouvez les anciens dossiers Excel et les lots suivis dans SmartTrace, chacun avec un QR code permanent. Les données historiques restent distinctes du stock actif.</p></div>
    <button className="ur-outline" type="button" onClick={()=>setRevision(n=>n+1)} disabled={loading}>↻ Actualiser</button>
   </header>
   <div className="ur-tools"><label>Rechercher un lot<input type="search" value={search} onChange={e=>{setSearch(e.target.value);setOffset(0)}} placeholder="Code, espèce, variété ou article…"/></label>
    <label>Origine<select value={kind} onChange={e=>pickKind(e.target.value)}><option value="all">Tous les lots</option><option value="historical">Historique Excel</option><option value="operational">Production active</option></select></label></div>
   {error&&<div className="ur-error" role="alert">{error}</div>}
   <div className="ur-list" aria-live="polite">
    {loading&&<p>Chargement des lots…</p>}
    {!loading&&result.items.length===0&&<div className="ur-empty"><b>Aucun lot dans le registre pour cette recherche.</b><p>Si des lignes Excel sont déjà présentes dans Atlas, utilisez « Reconstruire l’index ». Sinon, commencez par l'import dans Données sources.</p><button type="button" disabled={repairing} onClick={rebuild} className="ur-outline">{repairing?'Synchronisation…':'Reconstruire l’index des lots'}</button></div>}
    {!loading&&result.items.map(item=><article className="ur-card" key={item.id}>
      <div className="ur-card-main"><span className={'ur-tag '+(item.kind==='historical'?'ur-tag-old':'ur-tag-active')}>{item.kind==='historical'?'Historique Excel':'Production active'}</span>
       <h3>{item.kind==='historical'?'LOT '+item.code:item.code}</h3>
       <p>{item.species||'Espèce non renseignée'} · {item.article||item.varieties?.[0]||'Variété non renseignée'} · {item.campaign||'Campagne non renseignée'}</p>
       {item.kind==='historical'&&<small>{item.counts?.production||0} production · {item.counts?.greffage||0} greffage · {item.counts?.livraison||0} livraison(s) · Rapprochement par code à cinq chiffres</small>}
      </div>
      <div className="ur-actions"><button type="button" className="ur-primary" onClick={()=>item.kind==='historical'?onOpenHistorical(item.code):onOpenOperational(item.operationalLotId)}>Voir le dossier</button>
       <button type="button" className="ur-outline" onClick={()=>showQr(item)} disabled={qrBusy}>▦ QR code</button></div>
    </article>)}
   </div>
   <footer className="ur-footer"><span>{result.total} lots · {result.total?offset+1:0}–{Math.min(offset+30,result.total)} affichés</span><div><button disabled={offset===0||loading} onClick={()=>setOffset(n=>Math.max(0,n-30))}>Précédent</button><button disabled={offset+30>=result.total||loading} onClick={()=>setOffset(n=>n+30)}>Suivant</button></div></footer>
   <p className="ur-note">Un QR code est un accès au dossier après connexion, pas une preuve de qualité, d'origine physique ou de certification.</p>
   {qr&&<div className="ur-qr-backdrop" onMouseDown={()=>setQr(null)}><section className="ur-qr-dialog" role="dialog" aria-modal="true" aria-label="QR code du lot" onMouseDown={e=>e.stopPropagation()}>
      <button className="ur-close" type="button" aria-label="Fermer" onClick={()=>setQr(null)}>✕</button><h2>QR · {qr.item.code}</h2><p>Scannez ce code pour retrouver le dossier après connexion.</p>
      <img width="240" height="240" src={qr.image_data_url} alt={'QR code du lot '+qr.item.code}/>
      <p className="ur-small">La page nécessite une authentification et les droits appropriés.</p>
      <div className="ur-actions"><a className="ur-primary" href={qr.image_data_url} download={'QR-'+qr.item.code+'.png'}>Télécharger le QR</a><button className="ur-outline" type="button" onClick={()=>navigator.clipboard?.writeText(qr.target)}>Copier le lien</button></div>
    </section></div>}
 </section>
}
