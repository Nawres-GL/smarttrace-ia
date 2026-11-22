import React,{useState} from 'react';
import './assistant-nlp.css';
import './nlp-human-review.css';

const API=import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const EXAMPLES=[
  "Aujourd'hui, j'ai transféré 500 plants du lot RO-13877/25 de la chambre 2 vers la serre 4.",
  "On a perdu 50 plants du lot 13877 dans la serre 4.",
  "Germination du lot 13877 : 900 plants à 24°C et humidité 80% pendant 48 heures.",
  "Livrer 300 plants du lot RO-13877/25 au client Ferme Alpha."
];
const LABELS={seed:'Réception des semences',sowing:'Semis',germination:'Germination',transfer:'Transfert',
  loss:'Pertes',treatment:'Intervention',graft:'Greffage',quality:'Contrôle qualité',
  preparation:'Préparation',delivery:'Livraison',return:'Retour'};
const FIELD_LABELS={quantity:'Quantité',quantity_received:'Quantité reçue',quantity_sown:'Quantité semée',
  origin:'Origine',destination:'Destination',location:'Emplacement',temperature:'Température (°C)',
  humidity:'Humidité (%)',duration_hours:'Durée (heures)',received_on:'Date réception',
  observed_on:'Date d’observation',performed_on:'Date de l’intervention',grafted_on:'Date greffage',
  delivered_on:'Date livraison',rootstock_lot_id:'Lot porte-greffe',
  approved:'Décision qualité',sanitary_status:'État sanitaire',homogeneity:'Homogénéité',
  inspected_quantity:'Quantité inspectée',quantity_used:'Quantité greffons',
  intervention_type:'Type d’intervention',started_on:'Début germination',
  ended_on:'Fin germination',sown_on:'Date semis',species:'Espèce',variety:'Variété',
  tray_type:'Type de plateau',tray_count:'Nombre de plateaux',tray_capacity:'Capacité plateau',
  seed_lot_id:'Lot de semences',supplier:'Fournisseur',supplier_lot_number:'Lot fournisseur',
  client:'Client',reason:'Motif',approved_quantity:'Quantité approuvée',
  delivery_note:'Bon de livraison',order_reference:'Référence commande',
  preparation_id:'Préparation',return_on:'Date de retour'};
function display(v){return typeof v==='boolean'?(v?'Oui':'Non'):String(v);}

export default function AssistantNLP({token,onApply}){
  const [text,setText]=useState(EXAMPLES[0]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [result,setResult]=useState(null);
  const [chosenAction,setChosenAction]=useState('');
  async function interpret(e){
    e.preventDefault();setBusy(true);setError('');setResult(null);
    try{
      const r=await fetch(`${API}/api/nlp/interpret`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({text})});
      const json=await r.json().catch(()=>({}));
      if(!r.ok){const details=(json.errors||[]).map(x=>x.message).join(' · ');throw new Error(details||json.detail||'Impossible d’interpréter le texte.');}
      setResult(json);
      setChosenAction((json.allowed_actions||[]).includes(json.action) ? json.action : '');
    }catch(err){setError(err.message);}finally{setBusy(false);}
  }
  return <section className="nlp-page">
    <div className="nlp-heading"><div><div className="nlp-eyebrow">ROYAL PLANTS · ASSISTANT INTELLIGENT</div><h1>Décrivez votre opération.<br/><span>SmartTrace prépare le formulaire.</span></h1><p>Un brouillon vérifiable, jamais une action automatique. Les règles agricoles restent appliquées par FastAPI.</p></div><div className="nlp-art" aria-hidden="true"><span>✦</span><span>▦</span><span>✧</span></div></div>
    <div className="nlp-grid"><form className="nlp-card" onSubmit={interpret}>
      <div className="nlp-card-title"><b>01 · Votre description</b><span>Français · 1 opération à la fois</span></div>
      <label htmlFor="nlp-text" className="nlp-label">Décrivez ce qui s’est réellement passé</label>
      <textarea id="nlp-text" rows="7" minLength="12" maxLength="1500" required value={text} onChange={e=>{setText(e.target.value);setResult(null);setChosenAction('');}}/>
      <div className="nlp-examples"><strong>Essayer un exemple :</strong>{EXAMPLES.map((x,i)=><button type="button" key={i} onClick={()=>{setText(x);setResult(null);setChosenAction('');}}>Exemple {i+1}</button>)}</div>
      <button className="nlp-primary" type="submit" disabled={busy}>{busy?'Analyse en cours…':'Analyser la description →'}</button>
      {error&&<div className="nlp-alert" role="alert">{error}</div>}
      <p className="nlp-footnote">Le texte n’est pas enregistré dans les événements lors de cette analyse. Les informations restent à vérifier par un collaborateur autorisé.</p>
    </form>
    <div className="nlp-card nlp-results"><div className="nlp-card-title"><b>02 · Proposition structurée</b><span>{result?result.engine==='rules-v1'?'Extraction locale (baseline)':'CamemBERT + règles':'En attente'}</span></div>
      {!result?<div className="nlp-idle"><div className="nlp-idle-icon">✦</div><h3>Le résultat s’affichera ici</h3><p>Une fois votre texte analysé, nous afficherons l’opération détectée, le lot retrouvé et les champs à confirmer.</p></div>:
      <div className="nlp-result-body">
        <div className="nlp-intent"><small>OPÉRATION SUGGÉRÉE</small><strong>{LABELS[result.action]||'À clarifier'}</strong><span>{result.engine==='rules-v1'?'Signal heuristique, pas une probabilité calibrée':`Score indicatif : ${Math.round((result.transformer_intent_score||0)*100)} % · proposition à vérifier`}</span></div>
        <div className="nlp-lot"><b>Lot cité</b><span>{result.lot_reference||'Non précisé'}</span><b>Lot actif autorisé</b><span>{result.lot_id?'Identifié dans MongoDB':'À sélectionner manuellement si nécessaire'}</span></div>
        <h3>Champs extraits</h3><div className="nlp-fields">{Object.entries(result.fields||{}).map(([k,v])=><div key={k}><span>{FIELD_LABELS[k]||k}</span><strong>{display(v)}</strong></div>)}{!Object.keys(result.fields||{}).length&&<p>Aucun champ identifié.</p>}</div>
        {result.missing?.length>0&&<div className="nlp-review"><strong>À compléter dans le formulaire</strong><p>{result.missing.map(k=>FIELD_LABELS[k]||k).join(' · ')}</p></div>}
        {result.warnings?.map((w,i)=><div className="nlp-alert" key={i}>⚠ {w}</div>)}
        {result.transformer_intent&&<details className="nlp-diagnostics">
          <summary>Diagnostic CamemBERT (scores non calibrés)</summary>
          <p><b>Intention :</b> {result.transformer_intent} — {Math.round((result.transformer_intent_score||0)*100)} %</p>
          <p><b>Autres hypothèses :</b> {(result.transformer_alternatives||[]).map(v=>`${v.label} (${Math.round(v.score*100)} %)` ).join(' · ')}</p>
          <b>Entités proposées :</b>
          <div className="nlp-diagnostic-entities">
            {(result.transformer_entities||[]).map((v,i)=><div key={`${i}-${v.start}`}>
              <span>{v.label}</span><strong>{v.text}</strong><small>{Math.round(v.score*100)} %</small>
            </div>)}
          </div>
          <p>Une entité à score faible ne sera pas injectée dans le formulaire. Le parsing déterministe peut identifier des valeurs vérifiables.</p>
        </details>}
        <div className="nlp-review-panel">
          <label htmlFor="nlp-action-choice" className="nlp-label">Opération à ouvrir (modifiable par l'employé)</label>
          <select id="nlp-action-choice" className="nlp-action-select" value={chosenAction}
            disabled={!result.can_open_editor}
            onChange={e=>setChosenAction(e.target.value)}>
            <option value="">Choisir une opération autorisée…</option>
            {(result.allowed_actions||[]).map(key=><option key={key} value={key}>{LABELS[key]||key}</option>)}
          </select>
          <p className="nlp-footnote">{chosenAction && chosenAction!==result.action
            ? 'Vous avez modifié le type d’opération : les champs incertains seront laissés vides pour éviter un préremplissage erroné.'
            : 'Le formulaire peut être ouvert même si des champs manquent ou si le lot Excel n’a pas été retrouvé. Vous choisirez un lot actif autorisé.'}</p>
          {result.review_flags?.length>0&&<div className="nlp-hard-stop" role="alert">
            Cette description contient une négation, une question ou plusieurs opérations. Reformulez-la en une seule opération affirmative avant de continuer.
          </div>}
          <button type="button" className="nlp-primary" disabled={!result.can_open_editor||!chosenAction||!(result.allowed_actions||[]).includes(chosenAction)}
            onClick={()=>onApply({
              ...result,
              action:chosenAction,
              fields:chosenAction===result.action ? (result.fields||{}) : {},
              lot_id:chosenAction===result.action ? result.lot_id : null,
              ready_for_review:true
            })}>
            {result.can_open_editor ? 'Ouvrir le formulaire à compléter →' : 'Reformuler la description avant de continuer'}
          </button>
        </div>
        <p className="nlp-footnote">Aucune sauvegarde n’a eu lieu. Contrôlez toutes les valeurs, puis cliquez vous-même sur « Valider l’opération » dans la page correspondante.</p>
      </div>}
    </div></div>
    <div className="nlp-steps"><div><span>01</span><b>Comprendre</b><p>Intention + entités agricoles</p></div><div><span>02</span><b>Résoudre</b><p>Lot actif et droits d’accès</p></div><div><span>03</span><b>Réviser</b><p>Champs manquants + confirmation</p></div><div><span>04</span><b>Valider</b><p>Règles métier FastAPI</p></div></div>
  </section>;
}
