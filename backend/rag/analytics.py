"""Additional read-only analytical retrieval for SmartTrace Phase 7.

No AI-generated MongoDB pipelines, no writes, and no joins across physical
lots with the same historical five-digit reference.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite

# Keep analytics import independent from FastAPI and optional embedding packages.
from .structured import (campaign_from_question, evidence, normal,
                         site_scope)

MAX_OPERATIONAL_LOTS = 1500
MAX_GERMINATION_EVENTS = 3000
MAX_HISTORICAL_ROWS = 50000


def _positive_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and isfinite(value) and value >= 0:
        return float(value)
    return None


def _species_requested(question):
    normalized = normal(question)
    return 'tomate' if 'tomate' in normalized else None


def _matches_species(value, wanted):
    if not wanted:
        return True
    return wanted in normal(str(value or ''))


def operational_germination(question: str, db, user: dict):
    """Compute germinated/seeds from recorded GERMINATION events only.

    Returns (answer, evidence, warnings) or (None, [], []) if no usable events.
    Every MongoDB query is site-constrained for non-admin employees.
    """
    campaign = campaign_from_question(question)
    species = _species_requested(question)
    q = site_scope(user)
    if campaign:
        q = {**q, 'campaign': campaign}
    projection = {'_id': 1, 'code': 1, 'siteCode': 1, 'campaign': 1,
                  'species': 1, 'article': 1, 'variety': 1, 'lotType': 1}
    accessible = list(db.production_lots.find(q, projection).limit(MAX_OPERATIONAL_LOTS + 1))
    overflow_lots = len(accessible) > MAX_OPERATIONAL_LOTS
    relevant = [r for r in accessible[:MAX_OPERATIONAL_LOTS]
                if _matches_species(r.get('species'), species)
                and r.get('lotType', 'SEMIS') == 'SEMIS']
    if not relevant:
        return None, [], (['Analyse opérationnelle partielle : limite de lots atteinte.'] if overflow_lots else [])
    by_id = {r['_id']: r for r in relevant}
    event_query = {'subjectType': 'PRODUCTION_LOT', 'eventType': 'GERMINATION',
                   'subjectId': {'$in': list(by_id)}}
    if user.get('role') != 'admin':
        event_query.update(site_scope(user))
    projection_ev = {'_id': 1, 'subjectId': 1, 'siteCode': 1, 'details': 1}
    events = list(db.trace_events.find(event_query, projection_ev).limit(MAX_GERMINATION_EVENTS + 1))
    overflow_events = len(events) > MAX_GERMINATION_EVENTS
    # Only one valid germination operation per SEMIS lot by domain rule.
    per_lot = {}
    for ev in events[:MAX_GERMINATION_EVENTS]:
        lot = by_id.get(ev.get('subjectId'))
        if lot is None or ev.get('siteCode') != lot.get('siteCode'):
            continue
        details = ev.get('details') or {}
        sown = _positive_number(details.get('quantite_semee'))
        germinated = _positive_number(details.get('quantite_germee'))
        if sown is None or germinated is None or sown <= 0 or germinated > sown:
            continue
        per_lot.setdefault(lot['_id'], (lot, ev, sown, germinated))
    if not per_lot:
        warnings = []
        if overflow_lots or overflow_events:
            warnings.append('Analyse partielle : capacité de lecture du pilote dépassée.')
        return None, [], warnings

    groups = defaultdict(lambda: {'sown': 0., 'germinated': 0., 'events': []})
    for lot, ev, sown, germinated in per_lot.values():
        variety = str(lot.get('variety') or lot.get('article') or 'Variété non renseignée').strip()
        grp = groups[variety]
        grp['sown'] += sown
        grp['germinated'] += germinated
        grp['events'].append((lot, ev))
    ordered = sorted(groups.items(), key=lambda x: (-x[1]['germinated'] / x[1]['sown'], x[0]))
    answer = ['Taux de germination issus des événements opérationnels GERMINATION '
              '(quantité germée ÷ quantité semée ; pondérés par les semences, pas moyenne simple des lots).']
    if campaign:
        answer.append(f'Campagne filtrée : {campaign}.')
    if species:
        answer.append('Espèce filtrée : tomate.')
    sources = []
    for i, (variety, values) in enumerate(ordered[:10], 1):
        pct = 100 * values['germinated'] / values['sown']
        refs = ', '.join(str(ev['_id']) for _, ev in values['events'][:5])
        info = (f'{variety} : {pct:.1f} % ; {values["germinated"]:g} plantules germées / '
                f'{values["sown"]:g} semences ; {len(values["events"])} lot(s) ; '
                f'preuves événementielles {refs}')
        sources.append(evidence(f'mongo:germination:{i}', 'mongodb',
                                f'Germination — {variety}', info))
        answer.append(f'{i}. {info.split(" ; preuves événementielles")[0]} [{i}]')
    warnings = []
    if len(ordered) > 10 or overflow_lots or overflow_events:
        warnings.append('Résultats partiels : groupes ou enregistrements limités par le pilote.')
        answer.append('Résultats partiels : ne pas interpréter comme le total exhaustif.')
    return '\n'.join(answer), sources, warnings


def _reported_germination_rate(row: dict):
    """Read explicit Taux_Germination from the historical ETL raw_cells.

    Earlier ETL preserves raw_cells but does not promote the rate to top-level.
    No edits to the actual Excel file or existing ETL are needed.
    """
    if row.get('germination_rate_pct') is not None:
        return _positive_number(row['germination_rate_pct'])
    for cell in row.get('raw_cells') or []:
        if cell.get('column') == 'Taux_Germination':
            raw = cell.get('value')
            if isinstance(raw, str):
                raw = raw.strip().replace(',', '.').rstrip('%').strip()
                try:
                    raw = float(raw)
                except ValueError:
                    return None
            return _positive_number(raw)
    return None


def historical_reported_germination(question: str, user: dict):
    """Admin-only historical germination percentages from Excel's dedicated column."""
    if user.get('role') != 'admin':
        return None, [], []
    from app.history import indexes, summarize
    campaign = campaign_from_question(question)
    species = _species_requested(question)
    _, _, _, production_by_code, delivery_by_code, graft_by_code = indexes()
    groups = defaultdict(lambda: {'weighted_rate': 0., 'seeds': 0., 'rows': 0,
                                  'codes': set(), 'refs': []})
    inspected = 0
    for code, rows in production_by_code.items():
        if inspected >= MAX_HISTORICAL_ROWS:
            break
        if campaign:
            summary = summarize(code, rows, delivery_by_code.get(code, []), graft_by_code.get(code, []))
            if summary.get('campaign') != campaign:
                continue
        for row in rows:
            inspected += 1
            if inspected > MAX_HISTORICAL_ROWS:
                break
            if not _matches_species(row.get('species'), species):
                continue
            rate = _reported_germination_rate(row)
            weight = _positive_number(row.get('seeds_sown'))
            if rate is None or not (0 <= rate <= 100) or weight is None or weight <= 0:
                continue
            label = str(row.get('variety') or row.get('article') or 'Variété non renseignée').strip()
            grp = groups[label]
            grp['weighted_rate'] += rate * weight
            grp['seeds'] += weight
            grp['rows'] += 1
            grp['codes'].add(code)
            if len(grp['refs']) < 4:
                grp['refs'].append(str(row.get('source_row', '?')))
    if not groups:
        return None, [], []
    lines = [
        'Comparaison HISTORIQUE NON CERTIFIÉE : colonne Taux_Germination du fichier Excel de production.',
        'Pour chaque variété, moyenne pondérée par QteSemis_Rapport (semences semées) des taux déclarés ; '
        'il ne s’agit pas d’une mesure indépendante ni d’une certification agronomique.',
    ]
    if campaign:
        lines.append(f'Campagne : {campaign}.')
    if species:
        lines.append('Espèce : tomate.')
    sources = []
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1]['weighted_rate'] / kv[1]['seeds'], kv[0]))
    for i, (label, data) in enumerate(ranked[:10], 1):
        pct = data['weighted_rate'] / data['seeds']
        statement = (f'{label} : {pct:.1f} % (moyenne pondérée du taux Excel) ; '
                     f'{data["rows"]} ligne(s) ; {len(data["codes"])} code(s) de lot ; '
                     f'QteSemis_Rapport cumulée {data["seeds"]:g} ; lignes Excel {", ".join(data["refs"])}')
        lines.append(f'{i}. {statement} [{i}]')
        sources.append(evidence(f'excel:germination_rate:{i}', 'excel',
                                f'Taux de germination historique — {label}', statement))
    warnings = ['Taux_Germination : valeurs déclarées dans le fichier de production, non certifiées.']
    if len(ranked) > 10 or inspected > MAX_HISTORICAL_ROWS:
        warnings.append('Résultats partiels (limite de lignes du pilote).')
        lines.append('Résultats partiels (limite du pilote).')
    return '\n'.join(lines), sources, warnings


def historical_grafting_losses(question: str, user: dict, threshold_pct: int | None):
    """Admin-only historical graft-loss percentages, not operational stock-loss ratios."""
    if user.get('role') != 'admin':
        return None, [], []
    from app.history import indexes, summarize
    campaign = campaign_from_question(question)
    _, _, _, pi, di, gi = indexes()
    ranked = []
    visited = 0
    excluded_invalid = 0
    for code, rows in gi.items():
        if visited >= MAX_HISTORICAL_ROWS:
            break
        if campaign:
            summary = summarize(code, pi.get(code, []), di.get(code, []), rows)
            if summary.get('campaign') != campaign:
                continue
        for row in rows:
            visited += 1
            if visited > MAX_HISTORICAL_ROWS:
                break
            pct = _positive_number(row.get('total_loss_pct'))
            if pct is not None and pct > 100:
                excluded_invalid += 1
                continue
            if pct is None or (threshold_pct is not None and pct <= threshold_pct):
                continue
            ranked.append((pct, code, row))
    if not ranked:
        return None, [], []
    ranked.sort(key=lambda r: (-r[0], r[1]))
    sources, lines = [], [
        'Pertes HISTORIQUES de production greffée (Excel NON CERTIFIÉ) : '
        'colonne Perte_Totale, distincte du ratio pertes/semis des lots opérationnels.'
    ]
    if campaign:
        lines.append(f'Campagne : {campaign}.')
    if threshold_pct is not None:
        lines.append(f'Seuil strict : supérieur à {threshold_pct} %.')
    for i, (pct, code, row) in enumerate(ranked[:10], 1):
        statement = (f'Code {code} / ligne {row.get("source_row", "?")} : {pct:.1f} % de perte totale '
                     f'(greffage : {row.get("grafting_loss_pct", "inconnu")}) ; '
                     f'article {row.get("article") or "non renseigné"}')
        lines.append(f'{i}. {statement} [{i}]')
        sources.append(evidence(f'excel:grafting_loss:{code}:{row.get("source_row",i)}',
                                'excel', f'Greffage historique {code}', statement))
    warnings = []
    if excluded_invalid:
        warnings.append(f'{excluded_invalid} valeur(s) Perte_Totale hors de la plage 0–100 % exclue(s).')
    if len(ranked) > 10 or visited > MAX_HISTORICAL_ROWS:
        warnings.append('Résultats historiques limités aux dix premières lignes.')
        lines.append('Résultats partiels : lignes limitées.')
    return '\n'.join(lines), sources, warnings
