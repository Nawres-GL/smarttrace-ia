import React, {useEffect, useState} from 'react';
import './fabric.css';
const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const eventLabels = {RECEPTION_SEMENCES:'Réception des semences',SEMIS:'Semis',GERMINATION:'Germination',TRANSFERT:'Transfert',CONTROLE_QUALITE:'Contrôle qualité',QUALITY:'Contrôle qualité',LIVRAISON:'Livraison'};
function message(payload, status) {
  const detail=payload?.detail;
  return typeof detail==='string'?detail:Array.isArray(detail)?detail.map(x=>x.msg).join(' · '):`Erreur HTTP ${status}`;
}
async function get(token,path,signal) {
  const r=await fetch(`${API}${path}`,{headers:{Authorization:`Bearer ${token}`},signal});
  const body=await r.json().catch(()=>({}));
  if(!r.ok) throw Error(message(body,r.status));
  return body;
}
export default function BlockchainMonitor({token}) {
  const [counts,setCounts]=useState(null);
  const [lots,setLots]=useState([]);
  const [query,setQuery]=useState('');
  const [lotId,setLotId]=useState('');
  const [dossier,setDossier]=useState(null);
  const [proofs,setProofs]=useState({});
  const [busy,setBusy]=useState(false);
  const [verifying,setVerifying]=useState('');
  const [error,setError]=useState('');
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    if(!token)return;
    const ctrl=new AbortController();setError('');setBusy(true);
    Promise.all([
      get(token,'/api/blockchain/status',ctrl.signal),
      get(token,'/api/operations/lots?limit=500',ctrl.signal),
    ]).then(([status,records])=>{setCounts(status);setLots(Array.isArray(records)?records:[]);})
     .catch(e=>{if(!ctrl.signal.aborted)setError(e.message);})
     .finally(()=>{if(!ctrl.signal.aborted)setBusy(false);});
    return ()=>ctrl.abort();
  },[token,refresh]);
  useEffect(()=>{
    if(!lotId){setDossier(null);setProofs({});return;}
    const ctrl=new AbortController();setError('');setDossier(null);setProofs({});
    get(token,`/api/operations/lots/${encodeURIComponent(lotId)}`,ctrl.signal)
      .then(setDossier).catch(e=>{if(!ctrl.signal.aborted)setError(e.message);});
    return ()=>ctrl.abort();
  },[token,lotId]);
  const matching=lots.filter(l=>[l.code,l.species,l.variety,l.article,l.campaign].some(v=>String(v||'').toLowerCase().includes(query.toLowerCase())));
  const events=dossier?.events||[];
  async function verify(e) {
    if(!lotId||!e.id)return;
    setVerifying(e.id);setError('');
    try {
      const result=await get(token,`/api/blockchain/lots/${encodeURIComponent(lotId)}/events/${encodeURIComponent(e.id)}/verify`);
      setProofs(x=>({...x,[e.id]:result}));
    } catch(err) {setError(err.message);} finally {setVerifying('');}
  }
  const titles={VERIFIED:'Preuve vérifiée sur Fabric',LOCAL_MISMATCH:'Intégrité locale invalide',FABRIC_MISMATCH:'Preuve Fabric non concordante',UNAVAILABLE_OR_PENDING:'Preuve indisponible ou en attente'};
  return <section className="fabric-panel" aria-label="Suivi des preuves Fabric">
    <div className="fabric-monitor-heading"><div><h2>Suivi opérationnel &amp; preuves Fabric</h2><p>Les opérations sont enregistrées dans MongoDB dès leur validation. Fabric ajoute une preuve vérifiable : il ne crée pas de deuxième lot.</p></div>
      <button type="button" disabled={busy} onClick={()=>setRefresh(x=>x+1)}>Actualiser le statut</button></div>
    {error&&<p className="fabric-error" role="alert">{error}</p>}
    {busy&&<p role="status">Chargement des lots et du statut…</p>}
    {counts&&<>
      <p className="fabric-connection">{counts.network_configured?'Passerelle configurée · connexion réelle à vérifier':'Passerelle non configurée'}</p>
      <div className="fabric-stats">{Object.entries(counts.counts||{}).map(([key,v])=><div key={key}><b>{v}</b><small>{({PENDING:'En attente',CLAIMED:'En cours',RETRY:'À réessayer',COMMITTED:'Confirmés par le worker',INVALID_LOCAL:'Invalides localement'})[key]||key}</small></div>)}</div>
      <div className="fabric-explainer"><strong>Comment une preuve est-elle validée ?</strong><ol><li>Opération acceptée → enregistrée dans MongoDB.</li><li>Preuve en attente → événement placé dans la file Fabric.</li><li>Worker + passerelle en fonctionnement → soumission à Fabric, lecture et contrôle du hash.</li><li>Preuve vérifiée → transaction Fabric affichée; le lot MongoDB reste le même.</li></ol><p><strong>En attente ({counts.counts?.PENDING || 0}) :</strong> la validation métier est déjà enregistrée, mais la preuve n’a pas été confirmée. « Passerelle configurée » ne signifie pas que Fabric est connecté.</p></div><small>{counts.note}</small>
    </>}
    <div className="fabric-browser">
      <h3>Retrouver et vérifier un lot</h3>
      <p>Choisissez un lot du suivi opérationnel. Le registre historique Excel reste une source de consultation distincte : aucune ancienne opération ne devient certifiée par simple rapprochement.</p>
      <label>Rechercher par code, espèce, variété ou article
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Ex. TOMATE, RO-13877/25…" /></label>
      <label>Lot opérationnel
        <select value={lotId} onChange={e=>setLotId(e.target.value)}>
          <option value="">Choisir un lot… ({matching.length} résultat(s))</option>
          {matching.map(l=><option key={l.id} value={l.id}>{l.code||'Lot sans code'} · {l.species||'Espèce inconnue'} · {l.variety||'Variété non renseignée'}</option>)}
        </select>
      </label>
      {lotId&&!dossier&&<p>Chargement de la chronologie du lot…</p>}
      {dossier&&<div className="fabric-event-list"><h4>Chronologie du lot · {events.length} événement(s)</h4>
        {!events.length&&<p>Aucun événement enregistré pour ce lot.</p>}
        {events.map(e=>{const proof=proofs[e.id];return <div className="fabric-event-card" key={e.id}>
          <div className="fabric-event-title"><strong>{eventLabels[e.event_type]||e.event_type||'Événement'}</strong><small>{e.occurred_at?new Date(e.occurred_at).toLocaleString('fr-FR'):'Date non disponible'}</small></div>
          <p><strong>MongoDB :</strong> opération enregistrée · <strong>Fabric :</strong> {e.blockchain_status==='VERIFIE'?'confirmation enregistrée': 'preuve en attente / non vérifiée'}</p>
          <button type="button" disabled={!!verifying} onClick={()=>verify(e)}>{verifying===e.id?'Vérification…':'Vérifier sur Fabric'}</button>
          {proof&&<div role="status" className={proof.status==='VERIFIED'&&proof.verified?'fabric-ok':'fabric-pending'}>
            <strong>{titles[proof.status]||proof.status}</strong><p>Intégrité locale : {proof.local_hash_valid?'Valide':'Invalide ou non attestée'}. Fabric : {proof.verified?'Vérifié':'Non vérifié'}.</p>
            {proof.tx_id&&<small>Transaction : <code>{proof.tx_id}</code></small>}
          </div>}
        </div>})}
      </div>}
    </div>
    <p className="fabric-help">Les preuves ne sont affichées comme vérifiées qu'après consultation du registre Fabric et correspondance de l'événement. Ce panneau est en lecture seule.</p>
  </section>;
}
