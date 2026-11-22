import React,{useEffect,useState} from 'react';
import './data-intelligence.css';
import DataQualityWorkbench from './DataQualityWorkbench.jsx';
const API=import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const fmt=x=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(Number(x||0));
const initial={campaign:'',species:'',client:'',greenhouse:'',unit:''};
function Bars({title,rows=[],unit='',sample=false}){
  const max=Math.max(1,...rows.map(x=>x.value));
  return <section className="di-chart"><h3>{title}</h3>{rows.length ? rows.map((x,i)=><div className="di-bar-row" key={`${x.label}-${i}`}><span title={x.label}>{x.label}</span><div className="di-track"><div style={{width:`${Math.min(100,Math.max(0,100*x.value/max))}%`}}/></div><strong title={sample?`${x.sample_size||0} lignes utilisées`:''}>{fmt(x.value)}{unit}{sample&&<small className="di-sample"> · n={x.sample_size}</small>}</strong></div>):<p className="di-muted">Aucune donnée pour cette sélection.</p>}</section>;
}
function Filter({label,name,options=[],value,onChange}){return <label className="di-filter"><span>{label}</span><select value={value} onChange={e=>onChange(name,e.target.value)}><option value="">Toutes / tous</option>{options.map(x=><option key={x} value={x}>{x}</option>)}</select></label>}
export default function InsightsDashboard({token,revision=0}){
  const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const [filters,setFilters]=useState(initial);
  const change=(name,value)=>setFilters(p=>({...p,[name]:value}));
  useEffect(()=>{let live=true;const controller=new AbortController();setLoading(true);setError('');const params=new URLSearchParams(Object.entries(filters).filter(([,value])=>value));
    fetch(`${API}/api/insights/historique?${params}`,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal})
      .then(async r=>{const result=await r.json();if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:`Erreur HTTP ${r.status}`);return result})
      .then(result=>{if(live)setData(result)})
      .catch(e=>{if(live&&e.name!=='AbortError')setError(e.message)})
      .finally(()=>{if(live)setLoading(false)});
    return()=>{live=false;controller.abort()}
  },[token,revision,filters]);
  const kpis=data?.kpis;
  return <div className="di-panel"><div className="di-panel-head"><div><span className="di-kicker">ANALYSE HISTORIQUE</span><h2>Statistiques & insights</h2><p>Analyse descriptive de la production, des livraisons, du greffage et de la qualité des données importées dans Atlas.</p></div><button type="button" className="di-secondary" onClick={()=>setFilters({...initial})}>Réinitialiser les filtres</button></div>
    <div className="di-filters" aria-label="Filtres des statistiques"><Filter label="Campagne / année" name="campaign" options={data?.filter_options?.campaigns} value={filters.campaign} onChange={change}/><Filter label="Espèce" name="species" options={data?.filter_options?.species} value={filters.species} onChange={change}/><Filter label="Client (livraisons)" name="client" options={data?.filter_options?.clients} value={filters.client} onChange={change}/><Filter label="Unité de livraison" name="unit" options={data?.filter_options?.units} value={filters.unit} onChange={change}/><Filter label="Serre (greffage)" name="greenhouse" options={data?.filter_options?.greenhouses} value={filters.greenhouse} onChange={change}/></div>
    {loading&&<p className="di-muted" role="status">Mise à jour des indicateurs…</p>}
    {error&&<p className="di-note" role="alert">{error}</p>}
    {kpis&&!error&&<div className={loading?'di-loading':''}>
      <div className="di-kpis di-kpis-large">{[
        ['Lignes de production',kpis.production_rows],['Lignes de livraison',kpis.delivery_rows],['Lignes de greffage',kpis.grafting_rows],['Codes LOT distincts',kpis.distinct_lot_codes],
        ['Plants semés (source)',kpis.production_seeds_sown],['Plants nets de production',kpis.net_plants_production],['Bons de livraison distincts',kpis.delivery_notes],['Espèces en production',kpis.distinct_species]
      ].map(([label,value])=><div key={label}><b>{fmt(value)}</b><small>{label}</small></div>)}</div>
      <h3 className="di-section-label">Production</h3><div className="di-chart-grid"><Bars title="Quantités semées par espèce" rows={data.production_by_species}/><Bars title="Quantités semées par variété" rows={data.production_by_variety}/></div>
      <h3 className="di-section-label">Livraisons</h3><div className="di-chart-grid"><Bars title="Nombre de lignes par client" rows={data.delivery_lines_by_client}/><Bars title="Nombre de lignes par région" rows={data.delivery_lines_by_region}/><Bars title="Lignes par unité" rows={data.delivery_lines_by_unit}/>{filters.unit?<><Bars title={`Quantités par client (${filters.unit})`} rows={data.delivery_by_client}/><Bars title={`Quantités par région (${filters.unit})`} rows={data.delivery_by_region}/><Bars title={`Quantités par article (${filters.unit})`} rows={data.delivery_by_article}/><section className="di-chart"><h3>Quantités mensuelles (date document)</h3><div className="di-month-list">{(data.monthly_delivery||[]).map(x=><span key={x.label}><small>{x.label}</small><b>{fmt(x.value)}</b></span>)}</div></section></>:<p className="di-note">Choisissez une unité de livraison pour afficher les sommes de quantités sans mélanger des unités différentes.</p>}</div>
      <h3 className="di-section-label">Greffage</h3><div className="di-chart-grid"><Bars title="Taux moyen de greffage par serre" rows={data.graft_rate_by_greenhouse} unit=" %" sample/><Bars title="Perte moyenne de greffage par serre" rows={data.graft_loss_by_greenhouse} unit=" %" sample/></div>
      <h3 className="di-section-label">Qualité et rapprochement</h3><div className="di-kpis">{[['Livraisons sans correspondance',kpis.unlinked_delivery_rows],['Codes LOT ambigus',kpis.ambiguous_lot_codes],['Numéros LOT manquants',kpis.missing_lot_rows]].map(([label,value])=><div key={label}><b>{fmt(value)}</b><small>{label}</small></div>)}</div>
      {data.alerts?.length>0?<div className="di-alerts"><h3>Points à examiner</h3>{data.alerts.map(x=><p key={x.title}><strong>{x.title} — {fmt(x.count)}</strong><br/>{x.description}</p>)}</div>:<p className="di-positive">Aucune alerte de rapprochement détectée dans cette sélection.</p>}
      <div className="di-footnote">{data.notes?.map((x,i)=><p key={i}>{x}</p>)}</div>
    </div>}
    <DataQualityWorkbench token={token} revision={revision}/>
  </div>
}
