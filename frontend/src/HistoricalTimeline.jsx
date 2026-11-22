import React,{useMemo} from 'react';
import './historical-timeline.css';

/* Archived Excel observations, not operational audit events.
   Never infer a grafting date from 'DS. Réel' or create a missing event. */
export default function HistoricalTimeline({production=[],grafting=[],deliveries=[]}){
 const events=useMemo(()=>{
  const items=[];
  for(const p of production){
   if(p.sowing_date)items.push({date:p.sowing_date,label:'Semis indiqué dans l’archive',source:'Production',row:p.source_row,info:[p.lot_ref,p.seeds_sown!=null?`${p.seeds_sown} semences`:null].filter(Boolean).join(' · ')});
   if(p.germination_date_out)items.push({date:p.germination_date_out,label:'Sortie de germination indiquée',source:'Production',row:p.source_row,info:p.variety||p.article||''});
  }
  for(const d of deliveries){
   if(d.document_date)items.push({date:d.document_date,label:'Document de livraison',source:'Livraison',row:d.source_row,info:[d.delivery_note_number?'BL '+d.delivery_note_number:null,d.client,d.item_quantity!=null?String(d.item_quantity)+' '+(d.unit||''):null].filter(Boolean).join(' · ')});
  }
  for(const g of grafting){
   if(g.validated_on)items.push({date:g.validated_on,label:'Validation de ligne de greffage (source)',source:'Greffage',row:g.source_row,info:g.greenhouse?'Serre '+g.greenhouse:''});
  }
  return items.sort((a,b)=>String(a.date).localeCompare(String(b.date)));
 },[production,grafting,deliveries]);
 return <section className="ht-section" aria-label="Chronologie historique reconstituée"><h3>Chronologie historique <em>{events.length} observation(s) datée(s)</em></h3>
  <p className="ht-note">Événements reconstitués uniquement à partir des dates renseignées dans les archives. Les étapes absentes ne sont pas supposées réalisées. Les liens entre fichiers reposent sur le numéro de lot.</p>
  {!events.length&&<p>Les archives de ce lot ne contiennent aucune date interprétable pour construire une chronologie.</p>}
  <ol className="ht-list">{events.slice(0,80).map((event,i)=><li key={i}><span className="ht-date">{event.date}</span><div><b>{event.label}</b><p>{event.info||'Information complémentaire non renseignée'}</p><small>{event.source} · Ligne source n° {event.row??'—'}</small></div></li>)}</ol>
  {events.length>80&&<p className="ht-note">La chronologie est limitée aux 80 premières observations datées dans cette vue. Les autres lignes sont consultables dans les sections détaillées.</p>}
  <p className="ht-note">Les données de greffage sans véritable date explicite demeurent dans la section « Greffage » du dossier ; aucune date de greffage n'est inventée.</p>
 </section>
}
