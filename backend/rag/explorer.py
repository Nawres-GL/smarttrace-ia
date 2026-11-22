"""General allowlisted analytics for MongoDB and admin-only historical Excel.

No Mongo pipelines originate from a question or an LLM. Filtering and grouping
use only keys in catalog.py. All operational queries apply site restrictions
BEFORE materializing rows; historical Excel has a separate admin-only gate.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .catalog import CATALOG, Dataset, Metric

MAX_MONGO_SCAN = 15000
MAX_HISTORICAL_SCAN = 60000
MAX_FILTER_LENGTH = 120
MAX_SOURCE_ROWS = 5


class InvalidExplore(ValueError):
    pass


class ForbiddenExplore(PermissionError):
    pass


def _norm(text: Any) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text or '').casefold())
                   if not unicodedata.combining(c))


def _number(raw: Any, percentage: bool = False):
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip().replace('\u00a0','').replace(' ', '').replace(',', '.')
        raw = raw.rstrip('%')
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(v) or (percentage and not 0 <= v <= 100):
        return None
    return v


def _printed(value: float, rate: bool = False) -> str:
    if rate:
        return f'{value:.1f} %'
    if float(value).is_integer():
        return f'{int(value):,}'.replace(',', ' ')
    return f'{value:,.2f}'.replace(',', ' ').replace('.', ',')


def _str(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _month(value: Any) -> str:
    if hasattr(value, 'isoformat'):
        value = value.isoformat()
    value = _str(value)
    return value[:7] if re.match(r'^\d{4}-\d{2}', value) else ''


def _extract(record: dict, spec: Dataset, dimension: str) -> str:
    if dimension == 'month':
        return _month(record.get(spec.date_field))
    if dimension == 'lot_code' and spec.source == 'trace_events':
        return _str(record.get('subjectId'))
    field = spec.dimensions[dimension]
    return _str(record.get(field))


def _enrich_historical(source: str, record: dict, campaign: str | None) -> dict:
    if source == 'production':
        from .analytics import _reported_germination_rate
        value = _reported_germination_rate(record)
        # Don't mutate indexes() cached/shared raw ETL records.
        return {**record, 'campaign': campaign, 'germination_rate_pct': value}
    return {**record, 'campaign': campaign}


def _historical_records(spec: Dataset):
    from app.history import indexes, summarize
    production, delivery, graft, pi, di, gi = indexes()
    rows = {'production': production, 'delivery': delivery, 'grafting': graft}[spec.source]
    campaign_cache: dict[str, str | None] = {}
    for item in rows:
        code = item.get('lot_code')
        if code:
            if code not in campaign_cache:
                summary = summarize(code, pi.get(code, []), di.get(code, []), gi.get(code, []))
                campaign_cache[code] = summary.get('campaign')
            campaign = campaign_cache[code]
        else:
            campaign = item.get('campaign')
        yield _enrich_historical(spec.source, item, campaign)


def _germination_records(db, user: dict, filters: dict):
    # Join only by real operational lot ID, requiring identical site ownership.
    query = {} if user.get('role') == 'admin' else {
        'siteCode': {'$in': list(user.get('siteCodes', []))}}
    if filters.get('campaign'):
        query['campaign'] = filters['campaign'].upper()
    lots = list(db.production_lots.find(query, {
        '_id':1,'code':1,'siteCode':1,'campaign':1,'species':1,'article':1,'variety':1,
        'lotType':1}).limit(MAX_MONGO_SCAN+1))
    by_id = {r['_id']:r for r in lots[:MAX_MONGO_SCAN] if r.get('lotType','SEMIS') == 'SEMIS'}
    if not by_id:
        return []
    ev_query = {'subjectType':'PRODUCTION_LOT','eventType':'GERMINATION',
                'subjectId':{'$in':list(by_id)}}
    if user.get('role') != 'admin':
        ev_query['siteCode'] = {'$in':list(user.get('siteCodes', []))}
    events = list(db.trace_events.find(ev_query, {
        '_id':1,'subjectId':1,'siteCode':1,'details':1,'occurredAt':1}).limit(MAX_MONGO_SCAN+1))
    result = []
    seen = set()
    for ev in events:
        lot = by_id.get(ev.get('subjectId'))
        if not lot or lot.get('siteCode') != ev.get('siteCode') or lot['_id'] in seen:
            continue
        details = ev.get('details') or {}
        sown = _number(details.get('quantite_semee'))
        germinated = _number(details.get('quantite_germee'))
        if (sown is None or sown <= 0 or germinated is None or
                germinated < 0 or germinated > sown):
            continue
        result.append({'_id': ev['_id'], 'lotId':lot['_id'], 'code':lot.get('code'),
                       'campaign':lot.get('campaign'), 'siteCode':lot.get('siteCode'),
                       'species':lot.get('species'), 'article':lot.get('article'),
                       'variety':lot.get('variety'), 'occurredAt':ev.get('occurredAt'),
                       'quantitySown':sown, 'quantityGerminated':germinated})
        seen.add(lot['_id'])
    if len(lots) > MAX_MONGO_SCAN or len(events) > MAX_MONGO_SCAN:
        result.append({'_id':'__overflow__', '_overflow':True})
    return result


def _mongo_records(spec: Dataset, db, user: dict, filters: dict):
    if spec.source == 'operational_germination':
        return _germination_records(db, user, filters)
    if user.get('role') == 'admin':
        query = {}
    else:
        permitted_sites = [s for s in (user.get('siteCodes') or []) if isinstance(s, str)]
        query = {'siteCode': {'$in': permitted_sites}}
    # Use exact match for server-side fields when possible, never user-controlled operators.
    if 'campaign' in filters and 'campaign' in spec.dimensions:
        query[spec.dimensions['campaign']] = filters['campaign'].upper()
    if 'site' in filters and 'site' in spec.dimensions:
        requested = filters['site']
        if user.get('role') != 'admin' and requested not in (user.get('siteCodes') or []):
            raise ForbiddenExplore('Site non autorisé.')
        query['siteCode'] = requested
    # All other filters applied against allowlisted projected fields below.
    projection = {'_id': 1, 'siteCode': 1, spec.date_field: 1}
    for field in spec.dimensions.values():
        if field != 'month':
            projection[field] = 1
    for metric in spec.metrics.values():
        if metric.field and metric.field != 'pending':
            projection[metric.field] = 1
        if metric.denominator:
            projection[metric.denominator] = 1
    if 'pending' in spec.metrics:
        projection.update({'quantityReserved': 1, 'quantityDelivered': 1})
    projection['source_row'] = 1
    if spec.source in {'preparations', 'deliveries'}:
        projection['lotId'] = 1
    cursor = getattr(db, spec.source).find(query, projection).limit(MAX_MONGO_SCAN + 1)
    rows = list(cursor)
    if spec.source in {'preparations', 'deliveries'} and rows:
        lot_ids = sorted({r['lotId'] for r in rows if isinstance(r.get('lotId'), str)})
        if lot_ids:
            lot_query = {'_id': {'$in': lot_ids}}
            if user.get('role') != 'admin':
                lot_query['siteCode'] = {'$in': list(user.get('siteCodes') or [])}
            matches = list(db.production_lots.find(lot_query,
                              {'_id':1, 'code':1, 'siteCode':1}).limit(MAX_MONGO_SCAN + 1))
            by_id = {lot['_id']:lot for lot in matches}
            for row in rows:
                lot = by_id.get(row.get('lotId'))
                # Do not convert a UUID into a supposed lot code, nor join across sites.
                row['lotCodeReadable'] = (lot.get('code') if lot and
                                          lot.get('siteCode') == row.get('siteCode') else None)
    return rows


def _check_inputs(dataset: str, metric: str, group_by: str | None,
                  filters: dict[str, str], user: dict, limit: int, offset: int,
                  order: str):
    spec = CATALOG.get(dataset)
    if spec is None:
        raise InvalidExplore('Jeu de données inconnu. Consultez le catalogue RAG.')
    if user.get('role') not in spec.roles:
        raise ForbiddenExplore('Accès refusé à ce jeu de données.')
    if metric not in spec.metrics:
        raise InvalidExplore('Indicateur non disponible pour ce jeu de données.')
    if group_by is not None and group_by not in spec.dimensions:
        raise InvalidExplore('Regroupement non autorisé pour ce jeu de données.')
    if not isinstance(filters, dict) or len(filters) > 8:
        raise InvalidExplore('Filtres invalides (maximum huit).')
    for field, raw in filters.items():
        if field not in spec.dimensions or not isinstance(raw, str) or len(raw) > MAX_FILTER_LENGTH:
            raise InvalidExplore('Filtre ou valeur non autorisé.')
    if not (1 <= limit <= 50 and 0 <= offset <= 5000 and order in {'asc', 'desc'}):
        raise InvalidExplore('Pagination ou tri invalide.')
    return spec


def _filter(record: dict, spec: Dataset, filters: dict[str, str]) -> bool:
    for field, wanted in filters.items():
        observed = _extract(record, spec, field)
        if field == 'quality_status' and wanted == '__PENDING_QUALITY__':
            if _norm(observed) not in {'', 'non_controle', 'a_recontroler', 'non controle', 'a recontroler'}:
                return False
            continue
        if field == 'quality_status' and wanted == '__NOT_CONFORME__':
            if _norm(observed) == 'conforme':
                return False
            continue
        if field == 'lot_code':
            # Historical refs RO-13877/25 and raw code 13877 share only the 5-digit lookup key.
            observed_code = re.search(r'(?<!\d)\d{5}(?!\d)', observed)
            wanted_code = re.search(r'(?<!\d)\d{5}(?!\d)', wanted)
            if observed_code and wanted_code:
                if observed_code.group() != wanted_code.group():
                    return False
                continue
        # Campaign/site/status/lot codes and month are exact; names are partial text.
        if field in {'campaign','site','status','quality_status','lot_type','event_type',
                     'subject_type','lot_code','delivery_note','month','unit','type'}:
            if _norm(observed) != _norm(wanted):
                return False
        elif _norm(wanted) not in _norm(observed):
            return False
    return True


def _metric_value(record: dict, metric: Metric):
    if metric.kind == 'computed_sum':
        reserved = _number(record.get('quantityReserved'))
        delivered = _number(record.get('quantityDelivered'))
        if reserved is None or delivered is None or reserved < 0 or delivered < 0:
            return None
        return max(0., reserved - delivered)
    return _number(record.get(metric.field), percentage=(metric.kind == 'avg' and 'pct' in metric.field))


@dataclass
class Bucket:
    rows: int = 0
    valid: int = 0
    invalid: int = 0
    total: float = 0.0
    denom: float = 0.0
    unique: set = None
    refs: list = None

    def __post_init__(self):
        if self.unique is None:
            self.unique = set()
        if self.refs is None:
            self.refs = []

    def add(self, record: dict, metric: Metric, ref: str):
        self.rows += 1
        if len(self.refs) < MAX_SOURCE_ROWS:
            self.refs.append(ref)
        if metric.kind == 'count':
            self.valid += 1
            self.total += 1
            return
        if metric.kind == 'distinct':
            raw = record.get(metric.field)
            if raw is None or _str(raw) == '':
                self.invalid += 1
            else:
                self.unique.add(str(raw))
                self.valid += 1
            return
        val = _metric_value(record, metric)
        if val is None or val < 0:
            self.invalid += 1
            return
        if metric.kind == 'weighted_rate':
            denominator = _number(record.get(metric.denominator))
            if denominator is None or denominator <= 0 or val < 0:
                self.invalid += 1
                return
            # For explicit Excel percentage field val is in 0-100; for operational
            # loss ratio the numerator is a raw count and cannot exceed denominator.
            if metric.field.endswith('_pct'):
                if not 0 <= val <= 100:
                    self.invalid += 1
                    return
                self.total += val * denominator
            else:
                if val > denominator:
                    self.invalid += 1
                    return
                self.total += 100 * val
            self.denom += denominator
        else:
            self.total += val
        self.valid += 1

    def result(self, metric: Metric):
        if metric.kind == 'distinct':
            return float(len(self.unique)) if self.valid else None
        if metric.kind == 'count':
            return self.total
        if not self.valid:
            return None
        if metric.kind == 'avg':
            return self.total / self.valid
        if metric.kind == 'weighted_rate':
            return self.total / self.denom if self.denom > 0 else None
        return self.total


def _source_ref(record: dict, spec: Dataset) -> str:
    if spec.historical:
        return f'{spec.source}:ligne-{record.get("source_row","?")}:lot-{record.get("lot_code") or "sans-code"}'
    return f'{spec.source}:id-{_str(record.get("_id"))[:72]}'


def explore(dataset: str, metric: str, group_by: str | None, filters: dict[str, str],
            user: dict, db, limit: int = 10, offset: int = 0, order: str = 'desc',
            threshold: float | None = None) -> dict:
    """Return a response that uses the same shape as POST /api/rag/ask."""
    spec = _check_inputs(dataset, metric, group_by, filters, user, limit, offset, order)
    if threshold is not None and (not isinstance(threshold, (int, float)) or
                                  not math.isfinite(threshold) or abs(threshold) > 1e9):
        raise InvalidExplore('Seuil numérique invalide.')
    cap = MAX_HISTORICAL_SCAN if spec.historical else MAX_MONGO_SCAN
    if spec.historical:
        raw_records = list(_historical_records(spec))
    else:
        raw_records = _mongo_records(spec, db, user, filters)
    overflow = len(raw_records) > cap or any(rec.get('_overflow') for rec in raw_records)
    records = [rec for rec in raw_records[:cap] if not rec.get('_overflow')]
    chosen = [rec for rec in records if _filter(rec, spec, filters)]
    metric_spec = spec.metrics[metric]
    # Historical Qte is not summable across different units.
    partition_unit = (dataset == 'historical_deliveries' and metric == 'item_quantity'
                      and group_by != 'unit' and 'unit' not in filters)
    groups = defaultdict(Bucket)
    for rec in chosen:
        group = _extract(rec, spec, group_by) if group_by else 'Toutes les données'
        group = group or 'Non renseigné'
        if partition_unit:
            unit = _str(rec.get('unit')) or 'unité non renseignée'
            group = f'{group} · unité : {unit}'
        groups[group].add(rec, metric_spec, _source_ref(rec, spec))
    ranked = [(group, bucket, bucket.result(metric_spec)) for group,bucket in groups.items()]
    ranked = [(group,bucket,value) for group,bucket,value in ranked if value is not None]
    if threshold is not None:
        ranked = [(group,bucket,value) for group,bucket,value in ranked if value > float(threshold)]
    ranked.sort(key=lambda x: (x[2], _norm(x[0])), reverse=order == 'desc')
    selected = ranked[offset:offset+limit]
    sources = []
    lines = []
    data_rows = []
    kind = 'excel' if spec.historical else 'mongodb'
    if not selected:
        lines.append('Aucun résultat exploitable dans les enregistrements autorisés correspondant à ces filtres.'
                     if not overflow else
                     'Aucun résultat dans les lignes examinées (échantillon partiel, conclusion non exhaustive).')
    for i, (group, bucket, value) in enumerate(selected, 1):
        rate = metric_spec.kind in {'weighted_rate'} or (metric_spec.kind == 'avg' and 'pct' in metric_spec.field)
        statement = (f'{group} : {_printed(value, rate=rate)} '
                     f'({bucket.rows} ligne(s), {bucket.valid} valeur(s) valide(s), '
                     f'{bucket.invalid} ignorée(s)).')
        lines.append(f'{offset+i}. {statement} [{i}]')
        data_rows.append({'label': group if group != 'Toutes les données' else 'Total',
                          'value': round(value, 5), 'display': _printed(value, rate=rate),
                          'rows': bucket.rows, 'valid': bucket.valid,
                          'ignored': bucket.invalid, 'source_index': i})
        sid = hashlib.sha256(f'{dataset}:{metric}:{group}'.encode('utf-8')).hexdigest()[:15]
        sources.append({'id': f'{kind}:aggregate:{sid}', 'kind': kind,
                        'title': f'{spec.label} — {group}',
                        'excerpt': statement + ' Références sources : ' + ', '.join(bucket.refs),
                        'dataset': dataset, 'metric': metric, 'group': group,
                        'sample_source_refs': bucket.refs})
    prefix = f'{metric_spec.label} — {spec.label}.'
    prefix += ('\nHistorique Excel NON CERTIFIÉ; il ne prouve pas de généalogie ni de transaction Fabric.'
               if spec.historical else '\nSource : MongoDB opérationnel (données autorisées).')
    if filters:
        labels = [f'{key}={"différent de CONFORME" if value == "__NOT_CONFORME__" else value}'
                  for key, value in filters.items()]
        prefix += '\nFiltres : ' + ', '.join(labels) + '.'
    if group_by:
        prefix += f'\nRegroupement : {group_by}.'
    if metric_spec.description:
        prefix += f'\nMéthode : {metric_spec.description}'
    if threshold is not None:
        prefix += f'\nSeuil strict : supérieur à {_printed(float(threshold), rate=False)}.'
    prefix += f'\n{len(ranked)} groupe(s) avec un indicateur exploitable; affichage {offset+1} à {offset+len(selected)}.'
    warnings = []
    if overflow:
        warnings.append(f'Analyse PARTIELLE : lecture plafonnée à {cap} enregistrements; résultats non exhaustifs.')
    if offset + limit < len(ranked):
        warnings.append('Autres groupes disponibles : utilisez la pagination du tableau exploratoire.')
    skipped = sum(b.invalid for _,b,_ in ranked)
    if skipped:
        warnings.append(f'{skipped} valeur(s) manquante(s) ou incohérente(s) ignorée(s) dans les groupes retenus.')
    if partition_unit:
        warnings.append('Les quantités historiques sont séparées par unité, sans conversion automatique en plants.')
    return {'answer': prefix + '\n' + '\n'.join(lines), 'data_rows': data_rows,
            'metric_label': metric_spec.label, 'dataset_label': spec.label,
            'source_status': 'Historique Excel non certifié' if spec.historical else 'MongoDB opérationnel',
            'route': f'explorer:{dataset}', 'sources': sources, 'warnings': warnings,
            'retrieval_mode': 'excel_exact' if spec.historical else 'mongo_exact',
            'generation_mode': 'deterministe', 'read_only': True,
            'meta': {'dataset': dataset, 'metric': metric, 'group_by': group_by,
                     'filters': filters, 'total_groups': len(ranked), 'offset': offset,
                     'limit': limit, 'scanned': len(records),
                     'matching_records': len(chosen), 'complete_scan': not overflow,
                     'skipped_values': skipped, 'has_data': bool(selected)}}
