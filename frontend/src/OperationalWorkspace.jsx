import React, { useEffect, useMemo, useState } from 'react';
import './operations.css';
import './nlp-human-review.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const FR = new Intl.NumberFormat('fr-FR');
const fmt = n => FR.format(Number(n || 0));
const today = new Date().toLocaleDateString('en-CA');
const newForm = () => ({observed_on:today, started_on:today, ended_on:today,
  duration_hours:0, performed_on:today, grafted_on:today, inspected_on:today,
  delivered_on:today, returned_on:today, approved:'false',
  sanitary_status:'SAIN', homogeneity:'HOMOGENE', intervention_type:'ENTRETIEN',receipt_confirmed:'false'});
// Translate FastAPI/Pydantic responses without discarding field-level details.
const readableField = (name) => ({quantity:'Quantité',location:'Emplacement',origin:'Origine',destination:'Destination',duration_hours:'Durée',temperature:'Température',humidity:'Humidité',started_on:'Début germination',ended_on:'Fin germination',observed_on:'Date de mesure',inspected_on:'Date du contrôle',inspected_quantity:'Quantité inspectée',approved_quantity:'Quantité commercialisable',sanitary_status:'État sanitaire',homogeneity:'Homogénéité',approved:'Décision',notes:'Observations',rootstock_lot_id:'Lot porte-greffe'})[name] || name.replaceAll('_',' ');
function parseApiError(response, result) {
  const raw = result?.detail ?? result?.errors ?? result?.message;
  const issues = Array.isArray(raw) ? raw : Array.isArray(result?.errors) ? result.errors : [];
  const fields = {};
  const messages = [];
  for (const issue of issues) {
    const field = issue.field || (Array.isArray(issue.loc) ? issue.loc.filter(x => x !== 'body').join('.') : '');
    const label = readableField(field);
    const rawMessage = String(issue.message || issue.msg || 'Valeur invalide');
    const hint = issue.type === 'missing' ? 'Ce champ est obligatoire.' :
      issue.type?.includes('int_parsing') ? 'Saisissez un nombre entier.' :
      issue.type?.includes('date') ? 'Saisissez une date valide.' :
      issue.type?.includes('string_pattern') ? 'Format d’emplacement invalide.' :
      issue.type?.includes('greater_than') ? 'La valeur doit être strictement positive.' :
      issue.type?.includes('greater_than_equal') ? 'Valeur inférieure à la limite autorisée.' :
      issue.type?.includes('less_than_equal') ? 'Valeur supérieure à la limite autorisée.' : rawMessage;
    if (field) fields[field] = hint;
    messages.push(`${label} : ${hint}`);
  }
  let message = messages.join(' · ') || (typeof raw === 'string' ? raw : `Erreur HTTP ${response.status}. Vérifiez les champs.`);
  if (response.status === 401) message = 'Votre session a expiré. Reconnectez-vous.';
  if (response.status === 403) message = 'Vous n’avez pas l’autorisation pour cette opération ou ce site.';
  if (response.status >= 500) message = 'Le serveur est indisponible. Réessayez plus tard, sans répéter immédiatement une opération déjà enregistrée.';
  return { message, fields };
}
const defDateInvalid = (name,dateValue,action) => ({delivery:'delivered_on',return:'returned_on',treatment:'performed_on',graft:'grafted_on',quality:'inspected_on'}[action]===name && dateValue>today);
function validateAction(action, form, lot, dossier) {
  const errors = {};
  const put = (key, message) => { if (!errors[key]) errors[key] = message; };
  const required = actionDefinitions[action]?.fields || [];
  for (const f of required) {
    const v = form[f.name];
    if (f.required && (v === '' || v === undefined || v === null)) put(f.name, 'Ce champ est obligatoire.');
    if (f.type === 'number' && v !== '' && v !== undefined && v !== null) {
      if (!Number.isFinite(Number(v))) put(f.name, 'Saisissez un nombre valide.');
      else if (!Number.isInteger(Number(v)) && !['temperature','humidity','duration_hours'].includes(f.name)) put(f.name, 'Un nombre entier est requis.');
      else if (Number(v) < 0 || (['quantity','quantity_used'].includes(f.name) && Number(v) <= 0)) put(f.name, 'La quantité doit être positive.');
    }
  }
  const qty = Number(form.quantity);
  const locations = dossier?.lot?.locations || lot?.locations || {};
  const remaining = (name) => Math.max(0,Number(locations[name] || 0)-Number(dossier?.lot?.reserved_locations?.[name] || 0));
  const stock = Number(lot?.plants_in_stock ?? dossier?.lot?.plants_in_stock ?? 0);
  const reserved = Number(lot?.plants_reserved ?? dossier?.lot?.plants_reserved ?? 0);
  if (action === 'germination') {
    const sown = Number(lot?.quantity_sown ?? dossier?.lot?.quantity_sown);
    if (Number.isFinite(sown) && sown > 0 && qty > sown) put('quantity', `Maximum : ${sown} plants semés.`);
    if ((dossier?.events||[]).some(e=>e.event_type==='GERMINATION') || ['EN_PRODUCTION','CONFORME','BLOQUE','QUARANTAINE'].includes(lot?.status)) put('quantity','Germination déjà enregistrée pour ce lot.');
    if (form.started_on && form.ended_on && form.started_on > form.ended_on) put('ended_on','La fin doit suivre le début.');
    if (form.ended_on && form.observed_on && form.ended_on > form.observed_on) put('observed_on','La mesure doit suivre la fin de germination.');
    if (lot?.sown_on && form.started_on && form.started_on < lot.sown_on) put('started_on','La germination ne peut pas précéder le semis.');
    if (form.observed_on && form.observed_on > today) put('observed_on','Une observation réelle ne peut pas être dans le futur.');
    if (form.started_on && form.ended_on) {
      const max = (Math.round((new Date(form.ended_on)-new Date(form.started_on))/86400000)+1)*24;
      if (max >= 0 && Number(form.duration_hours) > max) put('duration_hours',`Durée incompatible avec les dates (maximum ${max} heures).`);
    }
    if (form.temperature !== '' && form.temperature != null && (Number(form.temperature) < -20 || Number(form.temperature) > 70)) put('temperature','Température autorisée : -20 à 70 °C.');
    if (form.humidity !== '' && form.humidity != null && (Number(form.humidity) < 0 || Number(form.humidity) > 100)) put('humidity','Humidité autorisée : 0 à 100 %.');
  }
  if (action === 'transfer' || action === 'loss' || action === 'preparation') {
    const location = action === 'transfer' ? form.origin : form.location;
    if (location && Object.keys(locations).length && !Object.hasOwn(locations, location)) put(action === 'transfer'?'origin':'location','Emplacement inconnu pour ce lot.');
    if (location && Object.keys(locations).length && Number(form.quantity) > remaining(location)) put('quantity',`Disponible hors réservations : ${remaining(location)} plants.`);
    if (reserved > 0 && ['transfer','loss'].includes(action)) put('quantity','Des préparations sont en cours : cette opération est bloquée.');
  }
  if (action === 'transfer') {
    if (form.origin && form.destination && form.origin.trim() === form.destination.trim()) put('destination','La destination doit être différente de l’origine.');
    if (stock <= 0) put('quantity','Enregistrez d’abord la germination ou vérifiez le stock.');
  }
  if (action === 'quality') {
    const inspected=Number(form.inspected_quantity), approved=Number(form.approved_quantity);
    if (inspected > stock) put('inspected_quantity',`Le stock disponible est de ${stock} plants.`);
    if (approved > inspected) put('approved_quantity','La quantité commercialisable ne peut pas dépasser la quantité inspectée.');
    if (form.approved === 'true' && (form.sanitary_status !== 'SAIN' || form.homogeneity !== 'HOMOGENE')) put('approved','Impossible de libérer ce lot tant que l’état sanitaire et l’homogénéité ne sont pas conformes.');
    if (form.approved === 'false' && approved !== 0) put('approved_quantity','Une décision non conforme implique 0 plant commercialisable.');
    if (form.approved === 'true' && approved <= 0) put('approved_quantity','Indiquez une quantité conforme strictement positive.');
    if (form.inspected_on && form.inspected_on > today) put('inspected_on','Le contrôle ne peut pas être dans le futur.');
    if ((form.notes || '').trim().length < 3) put('notes','Ajoutez au moins 3 caractères d’observation.');
    if (reserved > 0) put('inspected_quantity','Une préparation est en cours : contrôle non modifiable.');
  }
  if (action === 'preparation') {
    const approved = Number(lot?.quality_approved ?? 0), available = Math.max(0,approved-reserved);
    if (lot?.quality_status!=='CONFORME') put('quantity','Un lot doit être contrôlé et conforme avant préparation.');
    if (qty > available) put('quantity',`Maximum commercialisable non réservé : ${available} plants.`);
  }
  if (action === 'delivery' || action==='return') {
    const p=(dossier?.preparations||[]).find(x=>x.id===form.preparation_id);
    if (p) {
      const limit=action==='delivery'?Number(p.quantity_reserved)-Number(p.quantity_delivered):Number(p.quantity_delivered)-Number(p.quantity_returned||0);
      if (qty > limit) put('quantity',`Quantité maximale autorisée : ${Math.max(0,limit)} plants.`);
    }
  }
  if (['delivered_on','returned_on','performed_on','grafted_on','inspected_on'].some(k=>form[k]&&defDateInvalid(k,form[k],action))) {
    for (const k of ['delivered_on','returned_on','performed_on','grafted_on','inspected_on']) {
      if(form[k]&&defDateInvalid(k,form[k],action))put(k,'La date constatée ne peut pas être future.');
    }
  }
  if (action === 'delivery' && form.receipt_confirmed !== 'true') put('receipt_confirmed','La réception doit être explicitement confirmée avant validation.');
  if (action === 'graft' && Number(form.quantity_success) > Number(form.quantity_used)) put('quantity_success','La quantité réussie ne peut pas dépasser la quantité utilisée.');
  return errors;
}

const ruleHints={
 quantity:'Quantité positive. Ne dépassez pas le stock disponible ou la quantité semée selon l’opération.',
 location:'Choisissez un emplacement existant et accessible pour ce lot.',
 origin:'L’origine doit contenir la quantité indiquée (hors plants réservés).',
 destination:'Le nouvel emplacement doit être différent de l’origine.',
 started_on:'La date de début doit être au plus tôt celle du semis.',
 ended_on:'Fin de germination ≥ début et ≤ date d’observation.',
 observed_on:'Date de mesure ≥ fin de germination et ≤ aujourd’hui.',
 duration_hours:'Durée positive et cohérente avec l’intervalle des dates (max. 2 000 h).',
 temperature:'Entre −20 °C et 70 °C (selon la plage acceptée par l’application).',
 humidity:'Entre 0 et 100 %.',
 inspected_quantity:'Quantité inspectée ≤ stock du lot.',
 approved_quantity:'Quantité commercialisable ≤ quantité inspectée. Mettre 0 si non conforme.',
 approved:'Une libération conforme nécessite « Sain » et « Homogène ».',
 sanitary_status:'En cas d’anomalie sanitaire, ne choisissez pas « Conforme ».',
 homogeneity:'En cas d’hétérogénéité, ne choisissez pas « Conforme ».',
 inspected_on:'Date réelle ≥ semis et ≤ aujourd’hui.',
 performed_on:'Saisissez la date réelle de l’intervention.',
 grafted_on:'Saisissez la date du greffage constaté.',
 quantity_used:'La quantité utilisée doit être disponible dans chaque lot concerné.',
 quantity_success:'Les greffes réussies ne peuvent pas dépasser les quantités utilisées.',
 preparation_id:'Choisissez une préparation existante avec une quantité restante.',
 order_reference:'Indiquez une référence de commande unique pour ce lot et client.',
 receipt_confirmed:'La réception client doit être explicitement confirmée avant validation.',
 delivered_on:'Date de livraison ≥ semis et ≤ aujourd’hui.',
 returned_on:'Le retour doit suivre les livraisons réellement effectuées.',
 notes:'Ajoutez des observations factuelles. Le contrôle qualité exige au moins 3 caractères.',
 reason:'Décrivez le motif de manière vérifiable.',
};
const actionRules={
 germination:['Quantité germée ≤ quantité semée.','Semis ≤ début ≤ fin ≤ observation ≤ aujourd’hui.','Une germination ne peut être saisie qu’une fois par lot de semis.'],
 transfer:['Quantité transférée ≤ plants disponibles à l’origine, hors réservations.','Origine et destination doivent être différentes.','Transfert interdit si des préparations sont en cours.'],
 loss:['Pertes ≤ plants disponibles à l’emplacement, hors réservations.','Les préparations doivent être terminées ou annulées avant cette opération.'],
 treatment:['Utilisez une date réelle, un emplacement et un nom d’intervention.','Si c’est un traitement, renseignez aussi le produit et la dose.'],
 graft:['Greffes réussies ≤ greffes utilisées.','Les deux lots doivent être compatibles et les stocks suffisants.'],
 quality:['Quantité inspectée ≤ stock actuel.','Quantité commercialisable ≤ quantité inspectée.','Conforme uniquement si état sanitaire sain et homogénéité confirmée.'],
 preparation:['Le lot doit être conforme au contrôle qualité.','Quantité réservée ≤ stock disponible ET quantité commercialisable restante.'],
 delivery:['Quantité livrée ≤ restant sur la préparation, et ≤ stock réservé.','La réception client doit être confirmée. Date de livraison ≤ aujourd’hui.'],
 return:['Quantité retournée ≤ quantité livrée nette non encore retournée.','La date du retour ne peut précéder celle des livraisons.'],
};
const field = (name, label, type = 'text', required = true, options = null) => ({name,label,type,required,options});
const actionDefinitions = {
  germination: {title:'Enregistrer la germination', endpoint:'germination',role:'production',fields:[field('quantity','Plants germés','number'),field('location','Emplacement (ex : CHAMBRE-01)'),field('started_on','Début germination','date'),field('ended_on','Fin germination','date'),field('observed_on','Date de mesure','date'),field('duration_hours','Durée réelle (heures)','number'),field('temperature','Température °C','number',false),field('humidity','Humidité %','number',false),field('notes','Observations','textarea',false)]},
  transfer: {title:'Transférer des plants',endpoint:'transfer',role:'production',fields:[field('quantity','Quantité transférée','number'),field('origin','Emplacement d’origine'),field('destination','Nouvel emplacement'),field('notes','Observations','textarea',false)]},
  loss: {title:'Déclarer des pertes',endpoint:'loss',role:'production',fields:[field('quantity','Quantité perdue','number'),field('location','Emplacement'),field('reason','Motif de perte','textarea')]},
  treatment: {title:'Enregistrer une intervention',endpoint:'treatment',role:'production',fields:[field('name','Intervention'),field('intervention_type','Nature','select',true,[['ENTRETIEN','Entretien'],['TRAITEMENT','Traitement'],['OBSERVATION','Observation']]),field('location','Emplacement'),field('performed_on','Date opération','date'),field('product','Produit (obligatoire pour traitement)','text',false),field('dose','Dose appliquée','text',false),field('notes','Observations','textarea',false)]},
  graft: {title:'Enregistrer un greffage',endpoint:'graft',role:'production',fields:[field('rootstock_lot_id','Lot porte-greffe','lot'),field('scion_location','Emplacement des greffons'),field('rootstock_location','Emplacement porte-greffes'),field('quantity_used','Quantité utilisée','number'),field('quantity_success','Greffes réussies','number'),field('grafted_on','Date du greffage','date'),field('notes','Observations','textarea',false)]},
  quality: {title:'Contrôle qualité',endpoint:'quality',role:'qualite',fields:[field('approved','Décision','select',true,[['true','Conforme — libérable'],['false','Non conforme — bloqué']]),field('inspected_quantity','Quantité inspectée','number'),field('approved_quantity','Quantité commercialisable','number'),field('sanitary_status','État sanitaire','select',true,[['SAIN','Sain'],['A_SURVEILLER','À surveiller'],['NON_CONFORME','Non conforme']]),field('homogeneity','Homogénéité','select',true,[['HOMOGENE','Homogène'],['HETEROGENE','Hétérogène'],['A_VERIFIER','À vérifier']]),field('inspected_on','Date du contrôle','date'),field('notes','Observations qualité','textarea')]},
  preparation: {title:'Préparer une commande',endpoint:'preparation',role:'logistique',fields:[field('client','Client'),field('order_reference','Référence commande'),field('quantity','Quantité réservée','number'),field('location','Emplacement'),field('trays','Plateaux','number',false),field('pallets','Palettes','number',false)]},
  delivery: {title:'Confirmer une livraison',endpoint:'delivery',role:'logistique',fields:[field('preparation_id','Préparation','preparation'),field('quantity','Quantité livrée','number'),field('delivery_note','N° bon de livraison'),field('transporter','Transporteur'),field('vehicle','Véhicule'),field('received_by','Réceptionné par'),field('receipt_confirmed','Réception client confirmée','select',true,[['true','Oui — réception vérifiée'],['false','Non — ne pas valider']]),field('delivered_on','Date de livraison','date')]},
  return: {title:'Enregistrer un retour',endpoint:'return',role:'logistique',fields:[field('preparation_id','Préparation','preparation'),field('quantity','Quantité retournée','number'),field('reason','Motif','textarea'),field('returned_on','Date du retour','date')]},
};
const stages = [
  {key:'germination',label:'Germination',step:'01'},
  {key:'transfer',label:'Transfert en serre',step:'02'},
  {key:'loss',label:'Pertes',step:'03'},
  {key:'treatment',label:'Intervention',step:'04'},
  {key:'graft',label:'Greffage',step:'05'},
  {key:'quality',label:'Contrôle qualité',step:'06'},
  {key:'preparation',label:'Préparation',step:'07'},
  {key:'delivery',label:'Livraison',step:'08'},
  {key:'return',label:'Retour',step:'09'},
];
const eventLabels = {OUVERTURE_HISTORIQUE:'Ouverture sur stock vérifié',RECEPTION_SEMENCES:'Réception des semences', SEMIS:'Semis',GERMINATION:'Germination',TRANSFERT:'Transfert',PERTES:'Pertes',INTERVENTION:'Intervention',GREFFAGE:'Greffage',CONTROLE_QUALITE:'Contrôle qualité',PREPARATION:'Préparation',LIVRAISON:'Livraison',RETOUR:'Retour',NOTE_CORRECTION:'Note de correction'};

function FieldInput({f,value,onChange, lots, preparations, error, locations=[]}) {
  const common={name:f.name, id:`op-${f.name}`, value:value??'',onChange:e=>onChange(f.name,e.target.value), required:f.required,'aria-invalid':Boolean(error),'aria-describedby':error?`op-error-${f.name}`:undefined};
  if (f.type==='lot') return <select {...common}><option value="">Choisir un lot porte-greffe</option>{lots.map(l=><option value={l.id} key={l.id}>{l.code} · {l.variety}</option>)}</select>;
  if (f.type==='preparation') return <select {...common}><option value="">Choisir une préparation</option>{preparations.map(p=><option value={p.id} key={p.id}>{p.order_reference} · {p.client} · restant {fmt(p.quantity_reserved-p.quantity_delivered)}</option>)}</select>;
  if (f.type==='select') return <select {...common}><option value="">Sélectionner explicitement…</option>{f.options.map(([v,t])=><option key={v} value={v}>{t}</option>)}</select>;
  if (f.type==='textarea') return <textarea {...common} rows="3" minLength={f.name==='notes'&&f.required?3:undefined} placeholder={f.label}/>;
  return <><input {...common} type={f.type} step={f.type==='number'?(['temperature','humidity','duration_hours'].includes(f.name)?'any':'1'):undefined} min={f.type==='number'?(['temperature'].includes(f.name)?'-20':'0'):undefined} max={f.name==='humidity'?100:f.name==='temperature'?70:f.name==='duration_hours'?2000:f.type==='date'?today:undefined} list={['origin','destination','location','scion_location','rootstock_location'].includes(f.name)?`op-known-locations-${f.name}`:undefined} placeholder={f.label}/>{['origin','destination','location','scion_location','rootstock_location'].includes(f.name) && <datalist id={`op-known-locations-${f.name}` }>{locations.map(x=><option key={x} value={x}/>)}</datalist>}</>;
}

async function downloadInvestigation(token,lotId,format,setReportError,setExportBusy) {
  setExportBusy(format);setReportError('');
  try {
    const response=await fetch(`${API}/api/investigations/lots/${encodeURIComponent(lotId)}/export?format=${format}`,{headers:{Authorization:`Bearer ${token}`}});
    if(!response.ok){const result=await response.json().catch(()=>({}));throw new Error(typeof result.detail==='string'?result.detail:`Export impossible (HTTP ${response.status}).`);}
    const blob=await response.blob();const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=`fiche-enquete-${lotId}.${format}`;document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }catch(e){setReportError(e.message);}finally{setExportBusy('');}
}

function LotDetails({detail, qr, onClose, token}) {
  const {lot,events,preparations}=detail;
  const [reportError,setReportError]=useState('');
  const [exportBusy,setExportBusy]=useState('');
  return <div className="op-overlay" role="presentation" onMouseDown={onClose}><div className="op-drawer" role="dialog" aria-modal="true" aria-label={`Dossier du lot ${lot.code}`} onMouseDown={e=>e.stopPropagation()}>
    <div className="op-drawer-title"><div><div className="op-overline">DOSSIER NUMÉRIQUE · LOT ACTIF</div><h2>{lot.code}</h2><p>{lot.variety} · Site {lot.site_code}</p></div><button className="op-close" onClick={onClose} aria-label="Fermer">×</button></div>
    <div className="op-drawer-body">
      <div className="op-callout">Les opérations ci-dessous sont enregistrées dans MongoDB Atlas avec un journal d’audit horodaté. Les empreintes permettent un contrôle de cohérence local.</div>
      <div className="op-balance-grid">{[['Stock actuel',lot.plants_in_stock],['Réservés',lot.plants_reserved],['Livrés',lot.plants_delivered],['Pertes',lot.plants_lost]].map(([t,n])=><div className="op-balance" key={t}><span>{t}</span><strong>{fmt(n)}</strong></div>)}</div>
      {lot.historical_full_ref&&<div className="op-callout">Lot historique lié : <b>{lot.historical_full_ref}</b>. Les données Excel antérieures restent des archives distinctes.</div>}<div className="op-section-title">Situation qualité</div><div className="op-detail-row"><b>{lot.quality_status.replaceAll('_',' ')}</b><span>Commercialisables restantes : {fmt(lot.quality_approved)}</span></div>
      <div className="op-section-title">Fiche d’enquête externe</div>
      <p className="op-muted">Exporter un brouillon prérempli à partir des données opérationnelles. Les observations terrain et signatures restent à compléter. Ce document reste un brouillon, à compléter et à faire valider.</p>
      <div className="op-report-actions">
        <button type="button" disabled={!!exportBusy} onClick={()=>downloadInvestigation(token,lot.id,'pdf',setReportError,setExportBusy)}>{exportBusy==='pdf'?'Génération…':'Exporter en PDF'}</button>
        <button type="button" disabled={!!exportBusy} onClick={()=>downloadInvestigation(token,lot.id,'docx',setReportError,setExportBusy)}>{exportBusy==='docx'?'Génération…':'Exporter en Word'}</button>
      </div>
      {reportError&&<div className="op-error" role="alert">{reportError}</div>}
      <div className="op-section-title">Stocks par emplacement</div><div className="op-locations">{Object.entries(lot.locations).map(([name,quantity])=><span className="op-location" key={name}>{name} <b>{fmt(quantity)}</b></span>)}{!Object.keys(lot.locations).length&&<span>Germination non enregistrée.</span>}</div>
      <div className="op-section-title">Réservations de commandes</div>{preparations.length?preparations.map(p=><div className="op-detail-row" key={p.id}><b>{p.order_reference} — {p.client}</b><span>{fmt(p.quantity_delivered)} / {fmt(p.quantity_reserved)} livrés · {p.location}</span></div>):<p className="op-muted">Aucune commande préparée.</p>}
      <div className="op-section-title">Chronologie des opérations</div><div className="op-timeline">{events.map(e=><div className="op-event" key={e.id}><div className="op-event-icon">●</div><div><div className="op-event-header"><b>{eventLabels[e.event_type]||e.event_type}</b><time>{new Date(e.occurred_at).toLocaleString('fr-FR')}</time></div><div className="op-event-fields">{Object.entries(e.details||{}).filter(([k])=>k!=='parent_lot_ids').slice(0,9).map(([k,v])=><span key={k}>{k.replaceAll('_',' ')} : {String(v??'—')}</span>)}</div><small>Utilisateur : {e.actor_id} · <b>Événement journalisé</b></small></div></div>)}</div>
      <div className="op-section-title">QR Code du lot</div>{qr?<div className="op-qr"><img src={qr.image_data_url} alt={`QR du lot ${lot.code}`}/><div><b>{lot.code}</b><p>Après connexion, le scan ouvre ce dossier.</p><a href={qr.image_data_url} download={`QR-${lot.code}.png`}>Enregistrer le QR Code</a></div></div>:<p className="op-muted">Génération du QR Code…</p>}
    </div>
  </div></div>;
}

export default function OperationalWorkspace({token,userRole='production',mode='production',deepLink=null,onDeepLinkHandled=()=>{},nlpDraft=null,onNlpDraftConsumed=()=>{}}){
  const [seeds,setSeeds]=useState([]),[lots,setLots]=useState([]),[stats,setStats]=useState(null),[sites,setSites]=useState([]);
  const [selection,setSelection]=useState(''),[action,setAction]=useState('germination');
  const [form,setForm]=useState(newForm); 
  const [seedForm,setSeedForm]=useState({site_code:'S01',supplier:'',supplier_lot_number:'',species:'',variety:'',quantity_received:1000,received_on:today});
  const [lotForm,setLotForm]=useState({site_code:'S01',seed_lot_id:'',quantity_sown:600,sown_on:today,tray_type:'P104',tray_count:6,tray_capacity:104,substrate:'Tourbe'});
  const [legacy,setLegacy]=useState({lot_code:'',full_reference:'',site_code:'S01',stock_counted:0,location:'SERRE-01',verified_on:today,verification_note:''});
  const [detail,setDetail]=useState(null),[selectedRecord,setSelectedRecord]=useState(null),[qr,setQr]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [fieldErrors,setFieldErrors]=useState({});
  const [nlpReview,setNlpReview]=useState(null);
  const selectedLot = useMemo(()=>lots.find(l=>l.id===selection),[lots,selection]);
  const def = actionDefinitions[action];
  async function api(path,method='GET',body){
    const options={method,headers:{Authorization:`Bearer ${token}`}};
    if(body){options.headers['Content-Type']='application/json';options.headers['Idempotency-Key']=(globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}-${Math.random()}`);options.body=JSON.stringify(body);}
    const response=await fetch(`${API}${path}`,options), result=await response.json().catch(()=>({}));
    if(!response.ok){const parsed=parseApiError(response,result); const err=new Error(parsed.message);err.fields=parsed.fields;err.httpStatus=response.status;throw err;}
    return result;
  }
  async function refresh(){
    const [s,l,k,siteOptions]=await Promise.all([api('/api/seed-lots'),api('/api/operations/lots'),api('/api/operations/overview'),api('/api/sites')]);
    setSeeds(s);setLots(l);setStats(k);setSites(siteOptions);return l;
  }
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[token]);
  useEffect(()=>{if(!selection){setSelectedRecord(null);return;}api(`/api/operations/lots/${selection}`).then(setSelectedRecord).catch(e=>setError(e.message));},[selection,token]);
  useEffect(()=>{
    if(!deepLink||!lots.length)return;
    const found=lots.find(l=>l.id===deepLink);
    if(found){openDetail(found.id);}else{setError('Ce lot QR n’est pas accessible avec votre compte.');}
    onDeepLinkHandled();
  },[deepLink,lots]);
  async function openDetail(id){setBusy(true);setQr(null);try{const [details,code]=await Promise.all([api(`/api/operations/lots/${id}`),api(`/api/operations/lots/${id}/qr`)]);setDetail(details);setSelectedRecord(details);setQr(code);setSelection(id);}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function submitSeed(e){e.preventDefault();setError('');
    if(!seedForm.species.trim()||!seedForm.variety.trim()){setError('Renseignez séparément l’espèce et la variété des semences.');return}
    if(Number(seedForm.quantity_received)<=0 || !Number.isInteger(Number(seedForm.quantity_received))){setError('La quantité reçue doit être un entier strictement positif.');return}
    if(seedForm.received_on>today){setError('La date de réception ne peut pas être future.');return}
    setBusy(true);try{await api('/api/seed-lots','POST',{...seedForm,quantity_received:Number(seedForm.quantity_received)});setNotice('Lot de semences enregistré avec succès.');await refresh();}catch(err){setError(err.message);}finally{setBusy(false);}}
  async function submitLot(e){e.preventDefault();setError('');
    const seed=seeds.find(x=>x.id===lotForm.seed_lot_id);
    if(!seed){setError('Sélectionnez un lot de semences existant.');return}
    const available=Number(seed.quantity_received)-Number(seed.quantity_allocated);
    const sown=Number(lotForm.quantity_sown),capacity=Number(lotForm.tray_count)*Number(lotForm.tray_capacity);
    if(!Number.isInteger(sown)||sown<=0||sown>available){setError(`Quantité semée invalide : disponible ${fmt(available)} semences.`);return}
    if(!Number.isInteger(Number(lotForm.tray_count))||Number(lotForm.tray_count)<=0||!Number.isInteger(Number(lotForm.tray_capacity))||Number(lotForm.tray_capacity)<=0||sown>capacity){setError(`Capacité insuffisante : ${fmt(capacity)} places pour ${fmt(sown)} semences.`);return}
    if(lotForm.sown_on>today||lotForm.sown_on<seed.received_on){setError('Date de semis invalide : elle doit être comprise entre la réception et aujourd’hui.');return}
    setBusy(true);try{const x=await api('/api/lots','POST',{...lotForm,quantity_sown:Number(lotForm.quantity_sown),tray_count:Number(lotForm.tray_count),tray_capacity:Number(lotForm.tray_capacity)});setNotice(`Lot ${x.code} créé. Enregistrez ensuite la germination.`);const all=await refresh();setSelection(x.id);}catch(err){setError(err.message);}finally{setBusy(false);}}
  async function submitLegacy(e){e.preventDefault();setBusy(true);setError('');try{const result=await api('/api/operations/activate-history','POST',{...legacy,stock_counted:Number(legacy.stock_counted)});setNotice(`Lot Excel ${result.code} repris à partir du stock physiquement vérifié.`);await refresh();setSelection(result.id);}catch(err){setError(err.message);}finally{setBusy(false);}}
  async function submitAction(e){e.preventDefault();setError('');setFieldErrors({});try{
    if(!selection)throw new Error('Sélectionnez un lot opérationnel.');
    const validation=validateAction(action,form,selectedLot,selectedRecord);
    if(Object.keys(validation).length){setFieldErrors(validation);setError('Corrigez les champs signalés ci-dessous avant de valider.');return;}
    setBusy(true);
    const payload={};def.fields.forEach(f=>{let v=form[f.name];if(f.type==='number')v=(v===''||v===undefined||v===null)?null:Number(v);else if(f.name==='approved'||f.name==='receipt_confirmed')v=(v===''||v===undefined||v===null)?null:(v===true||v==='true');else if(v===undefined)v='';payload[f.name]=v;});
    const result=await api(`/api/operations/lots/${selection}/${def.endpoint}`,'POST',payload);
    setNotice(result.child_lot?`Opération enregistrée. Nouveau lot : ${result.child_lot.code}`:'Opération enregistrée et ajoutée à la chronologie du lot.');
    setForm(newForm());
    setNlpReview(null);
    await refresh();await openDetail(selection);
  }catch(err){setError(err.message);setFieldErrors(err.fields||{});}finally{setBusy(false);}}
  const update=(name,value)=>{setForm(x=>({...x,[name]:value}));setFieldErrors(prev=>{if(!prev[name])return prev;const copy={...prev};delete copy[name];return copy;});};
  const filteredStages=mode==='quality'?stages.filter(s=>s.key==='quality'):mode==='delivery'?stages.filter(s=>['preparation','delivery','return'].includes(s.key)):stages.filter(s=>['germination','transfer','loss','treatment','graft'].includes(s.key));
  useEffect(()=>{setAction(mode==='quality'?'quality':mode==='delivery'?'preparation':'germination');setForm(newForm());setFieldErrors({});},[mode]);

  // Receive a confirmed-to-review NLP draft. Never submit from this effect.
  useEffect(() => {
    if (!nlpDraft?.ready_for_review) return;
    const inputFields = nlpDraft.fields || {};
    if (nlpDraft.action === 'seed') {
      const allowed = new Set(Object.keys(seedForm));
      setSeedForm(prev => ({...Object.fromEntries(Object.keys(prev).map(key => [key, ''])),
        site_code:prev.site_code,
        ...Object.fromEntries(Object.entries(inputFields).filter(([key]) => allowed.has(key)))
      }));
    } else if (nlpDraft.action === 'sowing') {
      const allowed = new Set(Object.keys(lotForm));
      setLotForm(prev => ({...Object.fromEntries(Object.keys(prev).map(key => [key, ''])),
        site_code:prev.site_code,
        ...Object.fromEntries(Object.entries(inputFields).filter(([key]) => allowed.has(key)))
      }));
    } else if (actionDefinitions[nlpDraft.action]) {
      const allowed = new Set(actionDefinitions[nlpDraft.action].fields.map(f => f.name));
      // Approval and signed receipt must be explicitly confirmed; not inferred by AI.
      const protectedFields = new Set(['approved','approved_quantity','receipt_confirmed']);
      const safeFields = Object.fromEntries(Object.entries(inputFields)
        .filter(([key, value]) => allowed.has(key) && !protectedFields.has(key) && value !== null && value !== undefined));
      setAction(nlpDraft.action);
      // An NLP draft must NEVER silently fill missing dates with today's date.
      setForm({...Object.fromEntries(Object.keys(newForm()).map(key => [key, ''])),
        ...safeFields, approved:'', receipt_confirmed:''});
      // Avoid retaining a previous lot selection when NLP couldn't resolve one.
      setSelection(nlpDraft.lot_id || '');
    }
    setNlpReview({
      lot_reference:nlpDraft.lot_reference,
      missing:nlpDraft.missing||[],
      action:nlpDraft.action
    });
    setNotice('');
    onNlpDraftConsumed();
    const target = nlpDraft.action === 'seed' ? 'op-seed-editor'
      : nlpDraft.action === 'sowing' ? 'op-sowing-editor' : 'op-action-editor';
    requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({behavior:'smooth', block:'start'}));
  }, [nlpDraft]);
  return <div className="op-workspace">
    <div className="op-heading"><div><span className="op-overline">ROYAL PLANTS · GESTION OPÉRATIONNELLE</span><h1>{mode==='quality'?'Contrôle & libération':mode==='delivery'?'Préparation & livraisons':'Production en temps réel'}</h1><p>Enregistrez des événements vérifiables, maîtrisez les quantités et conservez l’historique de chaque lot.</p></div><span className="op-live">● Données Atlas · pilote</span></div>
    <div className="op-metrics">{[['Lots opérationnels',stats?.lots],['À contrôler',stats?.pending_quality],['Livraisons enregistrées',stats?.deliveries],['Événements journalisés',stats?.audit_events]].map(([t,v])=><div className="op-metric" key={t}><span>{t}</span><strong>{v===undefined||v===null?'—':fmt(v)}</strong></div>)}</div>
    {error&&<div className="op-flash error" role="alert" aria-live="assertive"><b>Opération non enregistrée :</b> {error}<button onClick={()=>setError('')}>×</button></div>}
    {notice&&<div className="op-flash success"><b>Succès :</b> {notice}<button onClick={()=>setNotice('')}>×</button></div>}
    {nlpReview&&<div className="op-nlp-review" role="status">
      <b>Brouillon créé par l'assistant NLP — aucune opération enregistrée.</b>
      <p>Vérifiez les valeurs, les dates, l'emplacement et le lot actif avant validation.
        {nlpReview.lot_reference?` Référence citée : ${nlpReview.lot_reference}.`:''}
        {nlpReview.missing.length?` Champs à compléter : ${nlpReview.missing.join(', ')}.`:''}
      </p>
      <button type="button" onClick={()=>setNlpReview(null)} aria-label="Masquer ce rappel">×</button>
    </div>}
    {mode==='production'&&<div className="op-columns">
      <div className="op-panel" id="op-seed-editor"><div className="op-panel-heading"><span className="op-numeral">01</span><div><h2>Réception des semences</h2><p>Enregistrer un nouveau lot fournisseur</p></div></div>
      <form onSubmit={submitSeed} className="op-form"><label>Site de production<select value={seedForm.site_code} required onChange={e=>setSeedForm(x=>({...x,site_code:e.target.value}))}>{sites.map(site=><option value={site.code} key={site.code}>{site.name} ({site.code})</option>)}</select></label>
        {[["supplier","Fournisseur"],["supplier_lot_number","N° lot fournisseur"],["species","Espèce"],["variety","Variété"]].map(([k,t])=><label key={k}>{t}<input required value={seedForm[k]} onChange={e=>setSeedForm(x=>({...x,[k]:e.target.value}))} placeholder={t}/></label>)}
        <div className="op-grid-two"><label>Quantité reçue<input required min="1" type="number" value={seedForm.quantity_received} onChange={e=>setSeedForm(x=>({...x,quantity_received:e.target.value}))}/></label><label>Date de réception<input required type="date" max={today} value={seedForm.received_on} onChange={e=>setSeedForm(x=>({...x,received_on:e.target.value}))}/></label></div>
        <div className="op-rule-card"><b>Règles · Réception</b>Indiquez une espèce et une variété distinctes, un fournisseur et son lot. La quantité reçue doit être positive ; la date doit correspondre à une réception réelle (jamais future).</div>
        <button className="op-primary" disabled={busy} type="submit">Enregistrer les semences <span>→</span></button>
      </form></div>
      <div className="op-panel" id="op-sowing-editor"><div className="op-panel-heading"><span className="op-numeral">02</span><div><h2>Création d’un lot</h2><p>Semis à partir de semences réceptionnées</p></div></div>
<form onSubmit={submitLot} className="op-form"><label>Site de production<select value={lotForm.site_code} required onChange={e=>setLotForm(x=>({...x,site_code:e.target.value,seed_lot_id:''}))}>{sites.map(site=><option value={site.code} key={site.code}>{site.name} ({site.code})</option>)}</select></label><label>Lot de semences<select required value={lotForm.seed_lot_id} onChange={e=>setLotForm(x=>({...x,seed_lot_id:e.target.value}))}><option value="">Sélectionner un lot</option>{seeds.filter(s=>s.site_code===lotForm.site_code).map(s=><option key={s.id} value={s.id}>{s.variety} · {s.supplier_lot_number} · disponibles {fmt(s.quantity_received-s.quantity_allocated)}</option>)}</select></label>
          <div className="op-grid-two"><label>Quantité semée<input min="1" required type="number" max={Math.max(0,Number(seeds.find(x=>x.id===lotForm.seed_lot_id)?.quantity_received||0)-Number(seeds.find(x=>x.id===lotForm.seed_lot_id)?.quantity_allocated||0))} value={lotForm.quantity_sown} onChange={e=>setLotForm(x=>({...x,quantity_sown:e.target.value}))}/></label><label>Date de semis<input required type="date" max={today} min={seeds.find(x=>x.id===lotForm.seed_lot_id)?.received_on} value={lotForm.sown_on} onChange={e=>setLotForm(x=>({...x,sown_on:e.target.value}))}/></label></div>
          <div className="op-grid-two"><label>Type de plateau<input required value={lotForm.tray_type} onChange={e=>setLotForm(x=>({...x,tray_type:e.target.value}))}/></label><label>Nombre de plateaux<input required type="number" min="1" value={lotForm.tray_count} onChange={e=>setLotForm(x=>({...x,tray_count:e.target.value}))}/></label><label>Capacité/plateau<input required type="number" min="1" value={lotForm.tray_capacity} onChange={e=>setLotForm(x=>({...x,tray_capacity:e.target.value}))}/></label><label>Substrat<input required value={lotForm.substrate} onChange={e=>setLotForm(x=>({...x,substrate:e.target.value}))}/></label></div><div className="op-rule-card"><b>Règles · Création du lot</b><ul><li>Quantité semée ≤ semences disponibles : <strong>{fmt(Math.max(0,Number(seeds.find(x=>x.id===lotForm.seed_lot_id)?.quantity_received||0)-Number(seeds.find(x=>x.id===lotForm.seed_lot_id)?.quantity_allocated||0)))}</strong>.</li><li>Quantité semée ≤ nombre de plateaux × capacité : <strong>{fmt(Number(lotForm.tray_count)*Number(lotForm.tray_capacity))}</strong>.</li><li>Date de réception ≤ date de semis ≤ aujourd’hui.</li></ul></div><button className="op-primary" disabled={busy} type="submit">Créer le lot de production <span>→</span></button>
        </form>
      </div>
    </div>}
    {mode==='production'&&userRole==='admin'&&<details className="op-panel op-historical-baseline"><summary className="op-panel-heading"><span className="op-numeral">↗</span><div><h2>Administration · Reprendre un lot Excel (facultatif)</h2><p>Uniquement si des plants existent encore et ont été physiquement comptés. Aucune opération passée n’est inventée.</p></div></summary>
      <form className="op-form op-baseline-form" onSubmit={submitLegacy}><label>Code à 5 chiffres<input required pattern="[0-9]{5}" placeholder="13766" value={legacy.lot_code} onChange={e=>setLegacy(x=>({...x,lot_code:e.target.value}))}/></label><label>Référence Excel complète<input required placeholder="RO-13766/25" value={legacy.full_reference} onChange={e=>setLegacy(x=>({...x,full_reference:e.target.value}))}/></label><label>Site<select value={legacy.site_code} onChange={e=>setLegacy(x=>({...x,site_code:e.target.value}))}>{sites.map(site=><option key={site.code} value={site.code}>{site.name}</option>)}</select></label><label>Stock compté<input type="number" required min="0" value={legacy.stock_counted} onChange={e=>setLegacy(x=>({...x,stock_counted:e.target.value}))}/></label><label>Emplacement<input required value={legacy.location} onChange={e=>setLegacy(x=>({...x,location:e.target.value}))}/></label><label>Date vérification<input type="date" required value={legacy.verified_on} onChange={e=>setLegacy(x=>({...x,verified_on:e.target.value}))}/></label><label className="op-wide">Justificatif du comptage<textarea required minLength="10" rows="2" value={legacy.verification_note} onChange={e=>setLegacy(x=>({...x,verification_note:e.target.value}))} placeholder="Qui a vérifié le stock et selon quel relevé ?"/></label><button className="op-primary" disabled={busy}>Activer le suivi de ce lot →</button></form></details>}
    <div className="op-columns main">
      <div className="op-panel"><div className="op-panel-heading"><span className="op-numeral">{mode==='production'?'03':'01'}</span><div><h2>Registre opérationnel</h2><p>{lots.length} lot(s) créés dans SmartTrace</p></div></div>
        <div className="op-list">{lots.map(l=><button className={`op-lot ${selection===l.id?'selected':''}`} key={l.id} onClick={()=>{setSelection(l.id);openDetail(l.id);}}><span className="op-lot-icon">✦</span><span className="op-lot-details"><strong>{l.code}</strong><small>{l.variety} · {l.site_code} · {l.quality_status.replaceAll('_',' ')}</small></span><span className="op-lot-count">{fmt(l.plants_in_stock)} <small>plants</small></span></button>)}{!lots.length&&<div className="op-empty">Aucun lot opérationnel. Créez-en un dans « Production ».</div>}</div>
      </div>
      <div className="op-panel" id="op-action-editor"><div className="op-panel-heading"><span className="op-numeral">{mode==='production'?'04':'02'}</span><div><h2>Nouvelle opération</h2><p>Contrôles métier avant validation</p></div></div>
        <div className="op-stage-picker">{filteredStages.map(s=><button type="button" onClick={()=>{setAction(s.key);setForm(newForm());setFieldErrors({});setError('');setNlpReview(null);}} className={action===s.key?'active':''} key={s.key}>{s.label}</button>)}</div>
        <form className="op-form" onSubmit={submitAction} key={`${mode}-${action}`}><label>Lot concerné<select required value={selection} onChange={e=>{setSelection(e.target.value);setDetail(null);}}><option value="">Choisir un lot</option>{lots.map(l=><option key={l.id} value={l.id}>{l.code} · {l.variety}</option>)}</select></label>
          <div className="op-active-title">{def.title}</div>
          <div className="op-rule-card" role="note"><b>Avant de valider cette opération</b><ul>{(actionRules[action]||[]).map((rule,i)=><li key={i}>{rule}</li>)}</ul>
          {selectedLot&&<div className="op-rule-summary">Stock actuel : {fmt(selectedLot.plants_in_stock)} · Réservés : {fmt(selectedLot.plants_reserved)} · Commercialisables : {fmt(selectedLot.quality_approved)}</div>}</div>
          <div className="op-form-grid">{def.fields.map(f=><label key={f.name} className={fieldErrors[f.name]?'op-has-error':''}>{f.label}<FieldInput f={f} value={form[f.name]??''} onChange={update} error={fieldErrors[f.name]} locations={Object.keys(selectedRecord?.lot?.locations||{})} lots={lots.filter(l=>l.id!==selection)} preparations={selectedRecord?.lot?.id===selection?selectedRecord.preparations:[]}/>{ruleHints[f.name]&&<small className="op-form-rule">{ruleHints[f.name]}</small>}{fieldErrors[f.name]&&<small id={`op-error-${f.name}`} className="op-field-error" role="alert">{fieldErrors[f.name]}</small>}</label>)}</div>
          {(action==='delivery'||action==='return')&&<div className="op-help">Ouvrez d’abord le dossier du lot pour charger ses préparations de commande.</div>}
          <button type="submit" disabled={busy||!selectedLot} className="op-primary">{busy?'Enregistrement…':'Valider l’opération'} <span>→</span></button>
          <div className="op-help">Validation humaine obligatoire · utilisateur identifié · événement inscrit dans le journal d’audit</div>
        </form>
      </div>
    </div>
    <div className="op-disclaimer"><b>Traçabilité responsable :</b> données historiques Excel en lecture seule · événements opérationnels dans Atlas · contrôle de cohérence local des événements · application pilote interne.</div>
    {detail&&<LotDetails detail={detail} qr={qr} token={token} onClose={()=>{setDetail(null);setQr(null);}}/>}
  </div>;
}
