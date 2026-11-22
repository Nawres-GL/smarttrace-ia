import React, { useEffect, useState } from 'react';
import './lot-history-filters.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

/** Filter selectors for the historical Excel registry; NEVER updates source workbooks. */
export default function LotHistoryFilters({ token, value, onChange, onReset }) {
  const [options, setOptions] = useState({ campaigns: [], species: [], articles: [], unknown_campaigns: 0 });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Dynamic cascading options: Campaign -> Species -> Article/Variety.
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ campaign: value.campaign || '', species: value.species || '' });
    setBusy(true);
    setError('');
    fetch(`${API}/api/historique/filters?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
    }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Impossible de charger les filtres.');
      return data;
    }).then(data => setOptions(data)).catch(err => {
      if (err.name !== 'AbortError') setError(err.message || 'Filtres indisponibles.');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [token, value.campaign, value.species]);

  return <div className="rp-history-filters" aria-label="Filtres du registre historique">
    <label>Campagne
      <select value={value.campaign || ''} onChange={e => onChange('campaign', e.target.value)}>
        <option value="">Toutes les campagnes</option>
        {(options.campaigns || []).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
        {(options.unknown_campaigns || 0) > 0 && <option value="__UNKNOWN__">Campagne indéterminée</option>}
      </select>
    </label>
    <label>Espèce
      <select value={value.species || ''} onChange={e => onChange('species', e.target.value)}>
        <option value="">Toutes les espèces</option>
        {(options.species || []).map(s => <option key={s} value={s}>{s}</option>)}
      </select>
    </label>
    <label>Article ou variété
      <select value={value.article || ''} onChange={e => onChange('article', e.target.value)}>
        <option value="">Tous les articles / variétés</option>
        {(options.articles || []).map(a => <option key={a} value={a}>{a}</option>)}
      </select>
    </label>
    <button type="button" className="rp-history-reset" onClick={onReset}>Effacer les filtres</button>
    {busy && <span className="rp-history-filter-note" role="status">Mise à jour des options…</span>}
    {error && <span className="rp-history-filter-error" role="alert">{error}</span>}
  </div>;
}
