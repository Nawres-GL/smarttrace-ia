import React, { useEffect, useMemo, useState } from 'react';
import './phase4.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const size = 24;

// Client displays server-filtered, paginated lot groups. The original Excel rows are untouched.
export default function HistoricalRegistry({ token, onOpen }) {
  const [campaign, setCampaign] = useState('');
  const [species, setSpecies] = useState('');
  const [article, setArticle] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [options, setOptions] = useState({ campaigns: [], species: [], articles: [], unknown_campaigns: 0 });
  const [result, setResult] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function get(path, signal) {
    const response = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` }, signal });
    const json = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(json.detail || `Erreur HTTP ${response.status}`);
    return json;
  }
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({campaign, species});
    get(`/api/historique/filters?${params}`, controller.signal)
      .then(setOptions).catch(e => {if (e.name !== 'AbortError') setError(e.message);});
    return () => controller.abort();
  }, [campaign, species, token]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError('');
      const params = new URLSearchParams({ campaign, species, article, search, offset:String(offset), limit:String(size) });
      get(`/api/historique/lots?${params}`, controller.signal)
        .then(setResult).catch(e => { if (e.name !== 'AbortError') setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 180);
    return () => {clearTimeout(timer); controller.abort();};
  }, [campaign, species, article, search, offset, token]);

  const groups = useMemo(() => {
    const speciesGroups = new Map();
    for (const lot of result.items) {
      const groupSpecies = species || lot.species_label || 'Non renseignée';
      const groupArticle = article || lot.article_label || 'Non renseigné';
      if (!speciesGroups.has(groupSpecies)) speciesGroups.set(groupSpecies, new Map());
      const articles = speciesGroups.get(groupSpecies);
      if (!articles.has(groupArticle)) articles.set(groupArticle, []);
      articles.get(groupArticle).push(lot);
    }
    return [...speciesGroups].map(([name, articles]) => ({name, articles:[...articles].map(([label, lots])=>({label, lots}))}));
  }, [result.items, species, article]);
  const reset = () => { setCampaign('');setSpecies('');setArticle('');setSearch('');setOffset(0); };
  const changeCampaign = v => {setCampaign(v);setSpecies('');setArticle('');setOffset(0);};
  const changeSpecies = v => {setSpecies(v);setArticle('');setOffset(0);};
  const changeArticle = v => {setArticle(v);setOffset(0);};

  return <section className="p4-registry" aria-label="Registre des lots historiques">
    <div className="p4-heading"><div><span className="p4-eyebrow">EXPLORATEUR DE PRODUCTION</span><h2>Lots classés par culture</h2><p>La liste s'affiche immédiatement. Affinez par campagne, espèce, article ou numéro de lot.</p></div><span className="p4-count">{result.total.toLocaleString('fr-FR')} lots</span></div>
    <div className="p4-filters">
      <label>Campagne
        <select value={campaign} onChange={e=>changeCampaign(e.target.value)} aria-label="Filtrer par campagne"><option value="">Toutes les campagnes</option>{options.campaigns.map(c=><option key={c.value} value={c.value}>{c.label}</option>)}{options.unknown_campaigns>0&&<option value="__UNKNOWN__">Campagne indéterminée</option>}</select>
      </label>
      <label>Espèce
        <select value={species} onChange={e=>changeSpecies(e.target.value)} aria-label="Filtrer par espèce"><option value="">Toutes les espèces</option>{options.species.map(s=><option key={s} value={s}>{s}</option>)}</select>
      </label>
      <label>Article / variété
        <select value={article} onChange={e=>changeArticle(e.target.value)} aria-label="Filtrer par article ou variété"><option value="">Tous les articles</option>{options.articles.map(a=><option key={a} value={a}>{a}</option>)}</select>
      </label>
      <label>Lot ou référence
        <input value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}} placeholder="13766 ou RO-13766/25" aria-label="Chercher un numéro de lot" />
      </label>
      <button type="button" className="p4-reset" onClick={reset}>Réinitialiser</button>
    </div>
    <p className="p4-footnote">La campagne d'un lot de production est basée sur sa date de semis (01/10 → 30/09). En l'absence de semis, une autre date disponible peut servir de référence. Le rapprochement Excel reste fondé uniquement sur le code à cinq chiffres.</p>
    {error&&<div className="p4-alert" role="alert">{error}</div>}
    {loading&&<div className="p4-loading">Chargement des lots…</div>}
    {!loading&&groups.length===0&&<div className="p4-empty">Aucun lot pour ces filtres. Essayez une autre campagne ou réinitialisez.</div>}
    <div className="p4-groups">{groups.map(g=><section className="p4-species" key={g.name}><header><span className="p4-species-badge">✦</span><h3>{g.name}</h3><span>{g.articles.reduce((n,a)=>n+a.lots.length,0)} lots affichés</span></header>{g.articles.map(a=><div className="p4-article" key={a.label}><div className="p4-article-title"><h4>{a.label}</h4><span>{a.lots.length} lot(s) sur cette page</span></div><div className="p4-lot-grid">{a.lots.map(l=><button type="button" className="p4-lot" onClick={()=>onOpen(l.lot_code)} key={l.lot_code}><div className="p4-lot-top"><b>LOT {l.lot_code}</b><span>{l.campaign||'Campagne ?'}</span></div><strong>{l.lot_refs[0]||l.graft_refs[0]||l.lot_code}</strong><div className="p4-lot-bottom"><span>Production {l.production_rows}</span><span>Greffage {l.grafting_rows}</span><span>Livraisons {l.delivery_rows}</span></div></button>)}</div></div>)}</section>)}</div>
    <footer className="p4-pagination"><span>{result.total===0?'Aucun résultat':`Lots ${offset+1} à ${Math.min(offset+size,result.total)} sur ${result.total}`}</span><div><button disabled={offset===0||loading} onClick={()=>setOffset(o=>Math.max(0,o-size))}>Précédent</button><button disabled={offset+size>=result.total||loading} onClick={()=>setOffset(o=>o+size)}>Suivant</button></div></footer>
  </section>;
}
