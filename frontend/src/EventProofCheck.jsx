import React,{useState} from 'react';
import './fabric.css';
const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
export default function EventProofCheck({token,lotId,event}){
 const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function verify(){setBusy(true);setError('');try{
  const r=await fetch(`${API}/api/blockchain/lots/${encodeURIComponent(lotId)}/events/${encodeURIComponent(event.id)}/verify`,{headers:{Authorization:`Bearer ${token}`}});
  const d=await r.json();if(!r.ok)throw Error(d.detail||'Erreur de vérification');setData(d);
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <div className="fabric-event-proof"><span>{event.blockchain_status==='VERIFIE'?'Fabric : confirmation enregistrée':'Fabric : en attente'}</span>
  <button type="button" disabled={busy} onClick={verify}>{busy?'Vérification…':'Vérifier sur Fabric'}</button>
  {data&&<span className={data.verified?'fabric-ok':'fabric-pending'}>{({VERIFIED:'Preuve vérifiée',LOCAL_MISMATCH:'Intégrité locale invalide',FABRIC_MISMATCH:'Preuve différente',UNAVAILABLE_OR_PENDING:'Preuve inaccessible ou non encore confirmée'})[data.status]||data.status}{data.tx_id&&<code title="Transaction Fabric"> · tx {data.tx_id.slice(0,16)}…</code>}</span>}
  {error&&<span role="alert">{error}</span>}
 </div>;
}
