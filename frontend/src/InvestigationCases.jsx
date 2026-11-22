import React, {useEffect,useMemo,useState} from 'react';
import './investigation-cases.css';
const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
const today=new Date().toLocaleDateString('en-CA');
const blank={lot_id:'',subject:'',customer:'',region:'',claim_date:today};
const editable=['subject','customer','region','claim_date','planting_date','affected_quantity','prior_complaint','agronomic_notes','irrigation_notes','soil_notes','climate_notes','treatments_notes','investigation_notes','engineer_opinion','administrative_opinion','status'];
const labels={BROUILLON:'Brouillon',EN_COURS:'En cours',A_REVOIR:'À revoir',CLOTURE:'Clôturée'};
const inputs=[
  ['subject','Sujet de la réclamation','textarea','Décrivez précisément le défaut constaté (au moins 5 caractères).'],
  ['customer','Agriculteur / client','text','Nom du client concerné, si connu.'],
  ['region','Région','text','Lieu de plantation ou de livraison.'],
  ['claim_date','Date de réclamation','date','Ne peut pas être dans le futur.'],
  ['planting_date','Date de plantation','date','Ne peut pas être future ni postérieure à la réclamation.'],
  ['affected_quantity','Nombre de plants concernés','number','Quantité non négative : laisser vide si inconnue.'],
  ['prior_complaint','Réclamation antérieure','select','Indiquer Oui, Non, ou laisser à vérifier.'],
  ['agronomic_notes','Observations agronomiques','textarea','Préciser les constatations de terrain sans inventer de données.'],
  ['soil_notes','Nature du sol','textarea','Sableux, argileux ou autres observations.'],
  ['irrigation_notes','Irrigation et eau','textarea','Fréquence, salinité, excès ou manque d’eau.'],
  ['climate_notes','Conditions climatiques','textarea','Température, pluviométrie, vent et dates.'],
  ['treatments_notes','Fertigations et traitements','textarea','Produit, dose, dates et références disponibles.'],
  ['investigation_notes','Synthèse de l’enquête','textarea','Obligatoire avant de passer en « À revoir ».'],
  ['engineer_opinion','Avis de l’ingénieur','textarea','Avis explicite obligatoire avant clôture.'],
  ['administrative_opinion','Avis administratif','textarea','Avis explicite obligatoire avant clôture.'],
];
async function call(token,path,method='GET',body){
  const r=await fetch(API+path,{method,headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Échec de l’action (HTTP ${r.status})`);
  return data;
}
function Input({item,value,change}){
  const [key,label,type,help]=item;
  const common={id:'case-'+key,value:value??'',onChange:e=>change(key,e.target.value),placeholder:label};
  return <label className={'case-field '+(type==='textarea'?'case-wide':'')} htmlFor={'case-'+key}>
    <span>{label}</span>
    {type==='textarea'?<textarea {...common} rows={3}/>:type==='select'?<select {...common}>
      <option value="">À vérifier</option><option value="true">Oui</option><option value="false">Non</option>
    </select>:<input {...common} type={type} min={type==='number'?'0':undefined} max={type==='date'?today:undefined} step={type==='number'?'1':undefined}/>}
    <small>{help}</small>
  </label>;
}
export default function InvestigationCases({token,userRole,onOpenLot,initialLotId}){
  const [cases,setCases]=useState([]),[lots,setLots]=useState([]),[create,setCreate]=useState(blank),[selected,setSelected]=useState(null);
  const [draft,setDraft]=useState(null),[search,setSearch]=useState(''),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[refresh,setRefresh]=useState(0);
  const canEdit=['admin','production','qualite'].includes(userRole),canClose=['admin','qualite'].includes(userRole);
  useEffect(()=>{if(initialLotId)setCreate(c=>({...c,lot_id:initialLotId}));},[initialLotId]);
  useEffect(()=>{let active=true;Promise.all([call(token,'/api/investigations/cases'),call(token,'/api/operations/lots?limit=500')])
      .then(([c,l])=>{if(active){setCases(c);setLots(l)}}).catch(e=>{if(active)setError(e.message)});
    return()=>{active=false};},[token,refresh]);
  const matches=useMemo(()=>cases.filter(c=>[c.lotCode,c.subject,c.customer,c.region].some(x=>String(x||'').toLowerCase().includes(search.toLowerCase()))),[cases,search]);
  async function newCase(e){e.preventDefault();setBusy(true);setError('');setNotice('');
    try{const x=await call(token,'/api/investigations/cases','POST',create);setCreate(blank);setSelected(x);setDraft({...x});setNotice('Enquête créée : complétez les observations ci-dessous.');setRefresh(v=>v+1)}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function choose(c){setSelected(c);setDraft({...c});setError('');setNotice('')}
  function change(k,v){setDraft(d=>({...d,[k]:v}))}
  async function save(e){e.preventDefault();setError('');setNotice('');
    if(!canEdit)return;
    if(draft.planting_date&&draft.planting_date>draft.claim_date){setError('La plantation doit précéder la réclamation.');return}
    if(draft.status==='CLOTURE'&&(!draft.engineer_opinion?.trim()||!draft.administrative_opinion?.trim())){setError('Avis ingénieur et avis administratif requis pour clôturer.');return}
    const body=Object.fromEntries(editable.map(k=>[k,draft[k]??(k==='affected_quantity'||k==='planting_date'||k==='prior_complaint'?null:'')]));
    body.affected_quantity=body.affected_quantity===''?null:Number(body.affected_quantity);
    body.prior_complaint=body.prior_complaint===''||body.prior_complaint===null?null:body.prior_complaint===true||body.prior_complaint==='true';
    body.revision=selected.revision;
    setBusy(true);try{const updated=await call(token,'/api/investigations/cases/'+selected.id,'PATCH',body);setSelected(updated);setDraft({...updated});setNotice('Enquête enregistrée.');setRefresh(v=>v+1)}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function exportFile(fmt){if(!selected)return;setBusy(true);setError('');try{
    const r=await fetch(`${API}/api/investigations/cases/${encodeURIComponent(selected.id)}/export?format=${fmt}`,{headers:{Authorization:`Bearer ${token}`}});
    if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||'Export impossible')}
    const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=`enquete-${selected.lotCode}-${selected.id.slice(0,8)}.${fmt}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);
  }catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section className="case-page">
    <div className="case-heading"><div><span className="section-eyebrow">QUALITÉ · ENQUÊTES & RÉCLAMATIONS</span><h1>Suivi des réclamations</h1><p>Ouvrir, documenter, revoir et exporter une enquête liée à un lot. Aucune clôture ne constitue une signature numérique.</p></div><span className="case-count">{cases.length} dossier(s)</span></div>
    {error&&<div className="case-feedback bad" role="alert">{error}<button type="button" onClick={()=>setError('')} aria-label="Fermer l’alerte">×</button></div>}
    {notice&&<div className="case-feedback good" role="status">{notice}<button type="button" onClick={()=>setNotice('')} aria-label="Fermer le message">×</button></div>}
    {canEdit&&<details className="case-panel case-new"><summary>＋ Ouvrir une nouvelle enquête</summary><form className="case-create-grid" onSubmit={newCase}>
      <label>Lot opérationnel<select value={create.lot_id} required onChange={e=>setCreate(x=>({...x,lot_id:e.target.value}))}><option value="">Choisir un lot accessible…</option>{lots.map(l=><option key={l.id} value={l.id}>{l.code} · {l.variety||l.article||'Variété à compléter'}</option>)}</select><small>Recherchez d’abord un lot dans « Registre des lots » si nécessaire.</small></label>
      <label>Sujet de la réclamation<input required minLength={5} maxLength={240} value={create.subject} onChange={e=>setCreate(x=>({...x,subject:e.target.value}))} placeholder="Ex. croissance irrégulière après livraison"/></label>
      <label>Agriculteur / client<input value={create.customer} onChange={e=>setCreate(x=>({...x,customer:e.target.value}))}/></label>
      <label>Région<input value={create.region} onChange={e=>setCreate(x=>({...x,region:e.target.value}))}/></label>
      <label>Date de réclamation<input type="date" max={today} required value={create.claim_date} onChange={e=>setCreate(x=>({...x,claim_date:e.target.value}))}/></label>
      <button className="case-btn primary" disabled={busy||!create.lot_id}>Créer l’enquête →</button>
    </form></details>}
    <div className="case-layout"><div className="case-panel case-list-panel"><div className="case-list-title"><h2>Dossiers</h2><button className="case-btn minimal" onClick={()=>setRefresh(x=>x+1)}>↻ Actualiser</button></div><label className="case-search">Rechercher<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Lot, réclamation, client…"/></label>
      <div className="case-list">{matches.map(c=><button key={c.id} className={'case-list-item '+(selected?.id===c.id?'picked':'')} onClick={()=>choose(c)}><span><b>{c.lotCode}</b><small>{c.subject}</small><small>{c.customer||'Client non renseigné'} · {new Date(c.updatedAt).toLocaleDateString('fr-FR')}</small></span><span className={'case-status st-'+c.status}>{labels[c.status]||c.status}</span></button>)}{!matches.length&&<p className="case-empty">Aucune enquête correspondante.</p>}</div>
    </div><div className="case-panel case-editor">{!draft?<div className="case-empty"><h2>Sélectionnez une enquête</h2><p>Choisissez un dossier ou créez-en un pour ajouter observations et avis.</p></div>:<>
      <div className="case-editor-head"><div><span className="section-eyebrow">DOSSIER {draft.id?.slice(0,8)}</span><h2>{draft.lotCode}</h2><p>{draft.subject}</p></div><button className="case-btn minimal" onClick={()=>onOpenLot(draft.lotId)}>Voir le lot →</button></div>
      <div className="case-actions"><button className="case-btn" disabled={busy} onClick={()=>exportFile('pdf')}>↓ Exporter PDF</button><button className="case-btn" disabled={busy} onClick={()=>exportFile('docx')}>↓ Exporter Word</button></div>
      <form onSubmit={save} className="case-form"><div className="case-form-grid">{inputs.map(item=><Input key={item[0]} item={item} value={draft[item[0]]===true?'true':draft[item[0]]===false?'false':draft[item[0]]} change={change}/>)}</div>
      <label className="case-field case-wide"><span>Statut du dossier</span><select value={draft.status} disabled={!canEdit||selected.status==='CLOTURE'} onChange={e=>change('status',e.target.value)}><option value="BROUILLON">Brouillon</option><option value="EN_COURS">En cours</option><option value="A_REVOIR">À revoir</option>{canClose&&<option value="CLOTURE">Clôturée (revue interne)</option>}</select><small>Pour clôturer : avis de l’ingénieur et avis administratif obligatoires. La clôture ne remplace pas les signatures.</small></label>
      {canEdit&&selected.status!=='CLOTURE'&&<button className="case-btn primary case-save" type="submit" disabled={busy}>{busy?'Enregistrement…':'Enregistrer les modifications →'}</button>}
      </form></>}</div></div>
  </section>;
}
