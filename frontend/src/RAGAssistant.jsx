import React, { useEffect, useMemo, useRef, useState } from 'react';
import './rag-assistant.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const EXAMPLES = [
  'Combien de livraisons par client ?',
  'Combien de plants ont été semés par espèce ?',
  'Quel est le taux moyen de greffage par article ?',
  'Compare les taux de germination des variétés de tomates pour C25.',
  'Quels lots ont un ratio de perte supérieur à 30 % ?',
  'Quelles sont les étapes du contrôle qualité avant livraison ?',
  'Quel est l’historique complet du lot 13877 ?',
];

function DataTable({ table }) {
  if (!table?.rows?.length) return null;
  return <div className="rag-v4-tablewrap"><table className="rag-v4-table">
    <thead><tr>{table.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
    <tbody>{table.rows.map((row, i) => <tr key={i}>
      <td>{row.category}</td><td className="rag-v4-number">{row.value}</td>
      <td>{row.records}</td>
    </tr>)}</tbody>
  </table></div>;
}

function AnswerView({ entry }) {
  const hasPanels = !!entry.panels?.length;
  return <>
    <div className="rag-v4-response" role="status">{entry.summary || entry.answer}</div>
    {hasPanels ? entry.panels.map((panel, i) =>
      <section className="rag-v4-panel" key={i}>
        <h4>{panel.title}</h4><DataTable table={panel.result} />
        {!!panel.sources?.length && <details className="rag-sources"><summary>Justificatifs de cette vue ({panel.sources.length})</summary>
          <div className="rag-source-list">{panel.sources.map((source, j) =>
            <div className="rag-source" key={source.id || j}><b>{source.title}</b><p>{source.excerpt}</p></div>)}</div>
        </details>}
      </section>
    ) : <DataTable table={entry.table} />}
    {entry.provenance && <div className="rag-v4-provenance">
      <strong>Source : {entry.provenance.source}</strong>
      {entry.provenance.filters && <span>{entry.provenance.filters}</span>}
      {!entry.provenance.complete && <span>Analyse partielle : tous les enregistrements n'ont pas été parcourus.</span>}
    </div>}
    {!!entry.warnings?.length && <details className="rag-v4-warnings"><summary>Précisions et limites ({entry.warnings.length})</summary>
      <ul>{entry.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
    {!!entry.sources?.length && <details className="rag-sources">
      <summary>Voir les sources et justificatifs ({entry.sources.length})</summary>
      <div className="rag-source-list">{entry.sources.map((source, j) => <div className="rag-source" key={source.id || j}>
        <div><b>[{j + 1}] {source.title}</b><small>{source.kind === 'excel'
          ? 'Historique Excel · non certifié' : source.kind === 'mongodb'
          ? 'MongoDB opérationnel' : 'Document interne'}</small></div>
        <p>{source.excerpt}</p>
      </div>)}</div>
    </details>}
    {entry.interpreted_query && <details className="rag-v3-interpretation">
      <summary>Détails techniques de la recherche (pour diagnostic)</summary>
      <pre>{JSON.stringify(entry.interpreted_query, null, 2)}</pre>
    </details>}
  </>;
}


export default function RAGAssistant({ token }) {
  const [mode, setMode] = useState('chat');
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [catalog, setCatalog] = useState([]);
  const [dataset, setDataset] = useState('');
  const [metric, setMetric] = useState('');
  const [groupBy, setGroupBy] = useState('');
  const [sortOrder, setSortOrder] = useState('desc');
  const [limit, setLimit] = useState(10);
  const [filters, setFilters] = useState([{ field: '', value: '' }]);
  const [lastExplore, setLastExplore] = useState(null);
  const controller = useRef(null);
  const bottom = useRef(null);

  useEffect(() => {
    if (!token) return;
    const abort = new AbortController();
    fetch(`${API}/api/rag/catalog`, {
      headers: { Authorization: `Bearer ${token}` }, signal: abort.signal,
    }).then(async r => {
      if (!r.ok) throw new Error('Catalogue des données indisponible.');
      return r.json();
    }).then(data => setCatalog(data.datasets || []))
      .catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => abort.abort();
  }, [token]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [history]);
  useEffect(() => { if (!dataset && catalog.length) setDataset(catalog[0].id); }, [catalog, dataset]);

  const selected = useMemo(() => catalog.find(d => d.id === dataset), [catalog, dataset]);
  useEffect(() => {
    if (selected) {
      setMetric(m => selected.metrics.some(x => x.id === m) ? m : selected.metrics[0]?.id || '');
      setGroupBy(g => selected.dimensions.some(x => x.id === g) ? g : '');
      setFilters(f => f.map(row => ({
        field: selected.dimensions.some(x => x.id === row.field) ? row.field : '', value: row.value,
      })));
    }
  }, [selected]);

  async function request(path, payload, visibleQuestion, isExplore = false) {
    if (busy || !token) return;
    setError(''); setBusy(true);
    setHistory(h => [...h, { kind: 'human', text: visibleQuestion }]);
    const abort = new AbortController(); controller.current = abort;
    try {
      const response = await fetch(`${API}/api/rag/${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: abort.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
      setHistory(h => [...h, { kind: 'assistant', ...data }]);
      if (isExplore) setLastExplore(payload);
    } catch (e) {
      if (e.name !== 'AbortError') {
        setError(e.message || 'Service RAG inaccessible.');
        setHistory(h => [...h, { kind: 'assistant', answer: 'Erreur de recherche, aucun résultat confirmé.',
          sources: [], warnings: [], generation_mode: 'erreur' }]);
      }
    } finally {
      if (controller.current === abort) { controller.current = null; setBusy(false); }
    }
  }

  function ask(e) {
    e?.preventDefault();
    const clean = question.trim();
    if (clean.length < 8) return;
    setQuestion('');
    request('ask', { question: clean }, clean);
  }

  function explore(e, nextOffset = 0) {
    e?.preventDefault();
    if (!selected || !metric) return;
    const activeFilters = {};
    for (const f of filters) {
      if (f.field && f.value.trim()) activeFilters[f.field] = f.value.trim();
    }
    const payload = { dataset, metric, group_by: groupBy || null,
      filters: activeFilters, order: sortOrder, limit: Number(limit), offset: nextOffset };
    const metricName = selected.metrics.find(x => x.id === metric)?.label || metric;
    const groupName = selected.dimensions.find(x => x.id === groupBy)?.label || 'toutes les données';
    request('explore', payload, `${metricName} — ${selected.label}, par ${groupName}` +
      (Object.keys(activeFilters).length ? ` (${JSON.stringify(activeFilters)})` : '') +
      (nextOffset ? ` · page suivante` : ''), true);
  }

  async function loadMore() {
    if (!lastExplore || busy) return;
    const next = (lastExplore.offset || 0) + lastExplore.limit;
    const payload = { ...lastExplore, offset: next };
    request('explore', payload, `Résultats suivants — ${lastExplore.dataset}`, true);
  }

  function changeFilter(index, key, value) {
    setFilters(old => old.map((f, i) => i === index ? { ...f, [key]: value } : f));
  }

  const lastMeta = [...history].reverse().find(x => x.kind === 'assistant' && x.meta)?.meta;
  const showMore = lastExplore && lastMeta && lastMeta.dataset === lastExplore.dataset &&
    lastMeta.total_groups > lastMeta.offset + lastMeta.limit;

  return <section className="rag-page">
    <header className="rag-header">
      <span className="rag-eyebrow">PHASE 7 · RAG HYBRIDE · CONSULTATION EN LECTURE SEULE</span>
      <h1>Interroger SmartTrace</h1>
      <p>Interrogez les données autorisées, explorez des indicateurs ou retrouvez des procédures. Les sources historiques Excel sont non certifiées et réservées aux administrateurs.</p>
    </header>

    <div className="rag-v3-tabs" role="tablist" aria-label="Mode de consultation">
      <button role="tab" aria-selected={mode === 'chat'} className={mode === 'chat' ? 'active' : ''}
        onClick={() => setMode('chat')} type="button">Poser une question</button>
      <button role="tab" aria-selected={mode === 'explore'} className={mode === 'explore' ? 'active' : ''}
        onClick={() => setMode('explore')} type="button">Explorer les données</button>
    </div>

    {mode === 'explore' && <form className="rag-v3-explorer" onSubmit={e => explore(e)}>
      <div className="rag-v3-grid">
        <label>Jeu de données
          <select value={dataset} onChange={e => { setDataset(e.target.value); setFilters([{ field: '', value: '' }]); }}>
            {catalog.map(d => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select>
        </label>
        <label>Indicateur
          <select value={metric} onChange={e => setMetric(e.target.value)}>
            {(selected?.metrics || []).map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <label>Regrouper par
          <select value={groupBy} onChange={e => setGroupBy(e.target.value)}>
            <option value="">Sans regroupement</option>
            {(selected?.dimensions || []).map(dim => <option value={dim.id} key={dim.id}>{dim.label}</option>)}
          </select>
        </label>
        <label>Résultats par page
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}>
            {[10, 20, 50].map(n => <option value={n} key={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <div className="rag-v3-filter-heading">Filtres facultatifs</div>
      {filters.map((f, i) => <div className="rag-v3-filter" key={i}>
        <select aria-label={`Champ du filtre ${i + 1}`} value={f.field}
          onChange={e => changeFilter(i, 'field', e.target.value)}>
          <option value="">Sélectionnez un champ</option>
          {(selected?.dimensions || []).map(d => <option value={d.id} key={d.id}>{d.label}</option>)}
        </select>
        <input aria-label={`Valeur du filtre ${i + 1}`} value={f.value} maxLength={120}
          onChange={e => changeFilter(i, 'value', e.target.value)} placeholder="Ex. C25, TOMATE, Client..." />
        <button type="button" title="Supprimer le filtre" onClick={() => setFilters(a => a.filter((_, j) => j !== i))}>×</button>
      </div>)}
      <div className="rag-v3-actions">
        <button type="button" className="rag-v3-secondary" disabled={filters.length >= 5}
          onClick={() => setFilters(a => [...a, { field: '', value: '' }])}>+ Ajouter un filtre</button>
        <label className="rag-v3-sort">Ordre
          <select value={sortOrder} onChange={e => setSortOrder(e.target.value)}>
            <option value="desc">Décroissant</option><option value="asc">Croissant</option>
          </select>
        </label>
        <button type="submit" disabled={busy || !dataset || !metric}>Analyser les données</button>
      </div>
      <small>{selected?.description || 'Chargement du catalogue...'} Les filtres sont appliqués uniquement sur les champs autorisés.</small>
    </form>}

    <div className="rag-main">
      <div className="rag-conversation" aria-live="polite">
        {!history.length && <div className="rag-welcome">
          <span className="rag-icon">✧</span>
          <h2>Que souhaitez-vous savoir ?</h2>
          <p>Le moteur calcule les indicateurs sur les données accessibles. L'index documentaire retrouve les passages pertinents.</p>
          <div className="rag-prompts">{EXAMPLES.map(q => <button type="button" key={q}
            onClick={() => { setMode('chat'); setQuestion(q); }}>{q}</button>)}</div>
        </div>}
        {history.map((entry, i) => entry.kind === 'human' ?
          <div className="rag-msg rag-human" key={i}><span>Vous</span><p>{entry.text}</p></div> :
          <article className="rag-msg rag-ai" key={i}>
            <div className="rag-answer-title"><strong>SmartTrace IA</strong>
              <span>{entry.generation_mode === 'ollama' ? 'Synthèse LLM local' : 'Réponse fondée sur les données disponibles'}</span></div>
            <AnswerView entry={entry} />
            {entry.interpreted_query && <button type="button" className="rag-v4-explore-link"
              onClick={() => {
                const info = entry.interpreted_query;
                setDataset(info.dataset); setMetric(info.metric);
                setGroupBy(info.group_by || '');
                setFilters(Object.entries(info.filters || {}).map(([field, value]) => ({ field, value })));
                setMode('explore');
              }}>
              Modifier cette analyse dans l'explorateur
            </button>}
          </article>)}
        <div ref={bottom}/>
      </div>
      {showMore && <button className="rag-v3-more" type="button" onClick={loadMore} disabled={busy}>
        Afficher les groupes suivants ({lastMeta.total_groups} au total)
      </button>}
      {error && <div role="alert" className="rag-error">{error}</div>}
      {busy && <p className="rag-working" role="status">Recherche des sources autorisées…</p>}
      {mode === 'chat' && <form className="rag-composer" onSubmit={ask}>
        <label className="rag-label" htmlFor="rag-question">Votre question</label>
        <textarea id="rag-question" value={question} onChange={e => setQuestion(e.target.value)}
          rows={2} maxLength={800} disabled={busy} placeholder="Ex. Quantité livrée par client en campagne C25 ?" />
        <div className="rag-composer-bottom"><small>Lecture seule · aucune écriture · réponses limitées aux données disponibles</small>
          <button type="submit" disabled={busy || question.trim().length < 8}>Interroger →</button></div>
      </form>}
    </div>
  </section>;
}
