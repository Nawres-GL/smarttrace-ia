import React,{useEffect,useRef,useState} from 'react';
import './data-intelligence.css';
import {CorrectionQueue} from './DataQualityWorkbench.jsx';
const API=import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const TYPES=[{id:'production',title:'Production',file:'Production_franc_valid-3.xlsx'},{id:'livraison',title:'Livraisons',file:'LivraisonC25_Clean-walid.xlsx'},{id:'greffage',title:'Greffage',file:'Production_Greffee_Final_corrected-1.xlsx'}];
const fmt=x=>new Intl.NumberFormat('fr-FR').format(Number(x||0));
export default function SourceImports({token,onImported}){
  const [type,setType]=useState('production'),[file,setFile]=useState(null),[preview,setPreview]=useState(null);
  const [importsRevision,setImportsRevision]=useState(0);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[status,setStatus]=useState(null),[reviewed,setReviewed]=useState(false);
  const picker=useRef(null);
  const headers={Authorization:`Bearer ${token}`};
  const read=async r=>{const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Erreur HTTP ${r.status}`);return data};
  const refresh=()=>fetch(`${API}/api/historique/imports/status`,{headers}).then(read).then(setStatus).catch(e=>setMessage(e.message));
  useEffect(()=>{if(token)refresh()},[token]);
  const clear=()=>{setFile(null);setPreview(null);setReviewed(false);setMessage('');if(picker.current)picker.current.value=''};
  const selectType=k=>{setType(k);clear()};
  const pick=e=>{const chosen=e.target.files?.[0]||null;setFile(chosen);setPreview(null);setReviewed(false);setMessage('')};
  const send=async()=>{if(!file)return;setBusy(true);setMessage('');try{
    if(!file.name.toLowerCase().endsWith('.xlsx'))throw Error('Choisissez un fichier Excel .xlsx.');
    const response=await fetch(`${API}/api/historique/imports/${type}/preview`,{method:'POST',headers:{...headers,'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},body:file});
    setPreview(await read(response));setReviewed(false);
  }catch(e){setMessage(e.message)}finally{setBusy(false)}};
  const confirm=async()=>{if(!preview||!reviewed)return;setBusy(true);setMessage('');try{
    const result=await read(await fetch(`${API}/api/historique/imports/${type}/confirm/${preview.preview_id}`,{method:'POST',headers}));
    setMessage(`Import terminé : ${fmt(result.added_rows)} nouvelles lignes enregistrées dans Atlas ; ${fmt(result.duplicate_rows)} lignes ignorées. ${fmt(result.possible_corrections)} correction(s) potentielle(s) à revoir.`);
    clear();setMessage(`Import terminé : ${fmt(result.added_rows)} nouvelles lignes enregistrées dans Atlas ; ${fmt(result.duplicate_rows)} lignes ignorées. ${fmt(result.possible_corrections)} correction(s) potentielle(s) à revoir.`);
    refresh();setImportsRevision(x=>x+1);onImported?.();
  }catch(e){setMessage(e.message);if(String(e.message).includes('Réanalysez')){setPreview(null);setReviewed(false)}}finally{setBusy(false)}};
  return <section className="di-panel" aria-label="Import Excel vers MongoDB Atlas">
    <div className="di-panel-head"><div><span className="di-kicker">MISE À JOUR DES SOURCES</span><h2>Importer un fichier Excel</h2><p>1. Choisir la source · 2. Analyser les différences · 3. Vérifier et confirmer. Rien n’est ajouté avant confirmation.</p></div><button type="button" className="di-secondary" onClick={refresh} disabled={busy}>Actualiser les comptes</button></div>
    <div className="di-source-types">{TYPES.map(t=><button type="button" key={t.id} aria-pressed={type===t.id} className={type===t.id?'di-type active':'di-type'} onClick={()=>selectType(t.id)} disabled={busy}><strong>{t.title}</strong><span>{t.file}</span><small>{fmt(status?.counts?.[t.id])} lignes en base</small></button>)}</div>
    <label className="di-file" htmlFor="source-xlsx-input"><span>Fichier Excel (.xlsx) avec les colonnes originales</span><input ref={picker} id="source-xlsx-input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={pick} disabled={busy}/><small>{file?`${file.name} · ${fmt(file.size)} octets`:'Sélectionnez la version mise à jour de cette source.'}</small></label>
    <button className="di-primary" type="button" disabled={busy||!file} onClick={send}>{busy?'Traitement en cours…':'Analyser les lignes — sans importer'}</button>
    {preview&&<div className="di-preview" aria-live="polite"><div className="di-preview-title"><h3>Résultat de l'analyse</h3><span className="di-preview-pill">Aucune écriture effectuée</span></div>
      <div className="di-kpis"><div><b>{fmt(preview.received_rows)}</b><small>Lignes reçues</small></div><div><b>{fmt(preview.duplicate_rows)}</b><small>Déjà en base — ignorées</small></div><div><b>{fmt(preview.new_rows)}</b><small>Nouvelles — à ajouter</small></div><div><b>{fmt(preview.possible_corrections)}</b><small>Corrections possibles — en revue</small></div></div>
      <p>Après confirmation : <strong>{fmt(preview.resulting_rows)} lignes</strong> dans la collection {type}. {preview.new_lot_codes!=null&&<>Lignes nouvelles concernant <strong>{fmt(preview.new_lot_codes)} codes LOT</strong> distincts.</>}</p>
      {preview.sample_new_lots?.length>0&&<p className="di-preview-samples"><strong>Exemples de codes LOT ajoutés :</strong> {preview.sample_new_lots.join(' · ')}</p>}
      {preview.sample_new_source_rows?.length>0&&<p className="di-preview-samples"><strong>Exemples de lignes Excel nouvelles :</strong> {preview.sample_new_source_rows.join(', ')}</p>}
      {preview.sample_existing_source_rows?.length>0&&<p className="di-preview-samples"><strong>Exemples de lignes déjà présentes :</strong> {preview.sample_existing_source_rows.join(', ')}</p>}
      <p>Les lignes suspectées de correction (clé métier proche) sont mises en revue. Un changement de numéro de lot ou de référence peut ne pas être détecté automatiquement : vérifiez les échantillons avant confirmation. Les fichiers Excel originaux restent inchangés.</p>
      {preview.possible_corrections>0&&<p className="di-note">{fmt(preview.possible_corrections)} ligne(s) suspectées de correction seront mises en attente de revue humaine (elles ne seront pas insérées automatiquement).</p>}
      {preview.new_rows>0||preview.possible_corrections>0?<><label className="di-consent"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>J'ai vérifié les résultats : j'autorise l’ajout des nouvelles lignes et la mise en attente des corrections possibles.</span></label><button className="di-primary" type="button" disabled={busy||!reviewed} onClick={confirm}>Confirmer {fmt(preview.new_rows)} ajout(s) et {fmt(preview.possible_corrections||0)} revue(s)</button></>:<p className="di-positive">Tout est déjà présent : aucun import nécessaire.</p>}
    </div>}
    {message&&<p className="di-note" role="status">{message}</p>}
    {status?.source_mode!=='atlas'&&<p className="di-note">Mode actuel : fichiers Excel. Les nouvelles lignes sont ajoutées dans Atlas, mais ne sont pas visibles dans le registre tant que HISTORY_MODE=atlas n'est pas activé, après l'import initial complet.</p>}
    {status?.recent?.length>0&&<div className="di-recent"><h3>Derniers imports confirmés</h3><div className="di-scroll"><table><thead><tr><th>Source</th><th>Reçues</th><th>Ajoutées</th><th>Ignorées</th><th>Date</th></tr></thead><tbody>{status.recent.map((r,i)=><tr key={i}><td>{r.kind}</td><td>{fmt(r.receivedRows)}</td><td>{fmt(r.addedRows)}</td><td>{fmt(r.duplicateRows)}</td><td>{r.createdAt?new Date(r.createdAt).toLocaleString('fr-FR'):'—'}</td></tr>)}</tbody></table></div></div>}
    <CorrectionQueue token={token} revision={importsRevision} onResolved={()=>{refresh();onImported?.()}}/>
    <div className="di-footnote">Contrôle par empreinte de contenu et nombre d'occurrences, même si les lignes ont changé de place. Format des colonnes identique à la source validée obligatoire. Les imports sont réservés aux administrateurs.</div>
  </section>
}
