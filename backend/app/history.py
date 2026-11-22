"""Read-only production, delivery and grafted-production Excel lookup.

All three sources linked by FIVE-DIGIT LOT only; no changes to the original files.
A shared code is a candidate association, not proof of identical physical origin.
"""
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import os
import unicodedata
from fastapi import APIRouter, HTTPException, Query
from etl.pipeline import (make_production_record, make_delivery_record,
                          make_graft_record, lot_five_digits, digest_file)
from etl.xlsx_reader import rows
from app.campaigns import inferred_lot_campaign, campaign_bounds

router = APIRouter(prefix='/api/historique', tags=['Historique Excel'])
BASE = Path(__file__).resolve().parents[2]


def source_paths():
    return (
        Path(os.getenv('PRODUCTION_XLSX', str(BASE/'data'/'Production_franc_valid-3.xlsx'))),
        Path(os.getenv('DELIVERY_XLSX', str(BASE/'data'/'LivraisonC25_Clean-walid.xlsx'))),
        Path(os.getenv('GRAFT_XLSX', str(BASE/'data'/'Production_Greffee_Final_corrected-1.xlsx'))),
    )


@lru_cache(maxsize=2)
def from_excel(p_path: str, d_path: str, g_path: str, p_mtime: int, d_mtime: int, g_mtime: int):
    p, d, g = Path(p_path), Path(d_path), Path(g_path)
    p_hash, d_hash = digest_file(p), digest_file(d)
    production = [make_production_record(r, p_hash) for r in rows(p)]
    deliveries = [make_delivery_record(r, d_hash) for r in rows(d)]
    g_hash = digest_file(g) if g.is_file() else None
    grafts = [make_graft_record(r, g_hash) for r in rows(g)] if g_hash else []
    return production, deliveries, grafts


def load_historical():
    mode = os.getenv('HISTORY_MODE', 'excel').lower()
    if mode == 'atlas':
        from app.main import db
        if db is None:
            raise HTTPException(503, 'MongoDB Atlas non configuré.')
        return (list(db.historical_production_records.find({})),
                list(db.historical_delivery_lines.find({})),
                list(db.historical_grafting_records.find({})))
    if mode != 'excel':
        raise HTTPException(500, 'HISTORY_MODE doit être excel ou atlas.')
    p, d, g = source_paths()
    missing = [str(x) for x in (p, d) if not x.is_file()]
    if missing:
        raise HTTPException(503, 'Fichiers de production/livraison manquants dans data/ : ' + ', '.join(missing))
    # Optional by design: the grafting file can be added after the first two.
    # If a custom GRAFT_XLSX is configured, a typo should NOT be silently ignored.
    if os.getenv('GRAFT_XLSX') and not g.is_file():
        raise HTTPException(503, 'Fichier greffage configuré introuvable : ' + str(g))
    return from_excel(str(p), str(d), str(g), p.stat().st_mtime_ns,
                      d.stat().st_mtime_ns, g.stat().st_mtime_ns if g.is_file() else -1)


def indexes():
    p_rows, d_rows, g_rows = load_historical()
    p_index, d_index, g_index = defaultdict(list), defaultdict(list), defaultdict(list)
    for src, index in ((p_rows,p_index), (d_rows,d_index), (g_rows,g_index)):
        for row in src:
            if row.get('lot_code'):
                index[row['lot_code']].append(row)
    return p_rows, d_rows, g_rows, p_index, d_index, g_index


def summarize(code, prod, deliveries, grafts):
    refs = sorted({p['lot_ref'] for p in prod if p.get('lot_ref')})
    graft_refs = sorted({g['lot_ref'] for g in grafts if g.get('lot_ref')})
    p_article_keys = {p.get('article_key') for p in prod if p.get('article_key')}
    mismatches = sum(1 for d in deliveries if p_article_keys and d.get('article_key') not in p_article_keys)
    if len(refs) > 1:
        status = 'PLUSIEURS_REFERENCES'
    elif prod and deliveries:
        status = 'LOT_LIE'
    elif prod:
        status = 'PRODUCTION_SEULE'
    elif grafts and deliveries:
        status = 'GREFFE_LIVRAISON'
    elif grafts:
        status = 'GREFFE_SEULE'
    else:
        status = 'LIVRAISON_SEULE'
    # Classify a LOT with the most trustworthy source for its identity:
    # franc production > grafted production > delivery. Delivery labels often
    # differ in case, and an article mismatch must not silently reclassify a lot.
    identity_rows = prod or grafts or deliveries
    def labels(field, title=False):
        mapped = {}
        for row in identity_rows:
            raw = str(row.get(field) or '').strip()
            if raw:
                key = ''.join(ch for ch in unicodedata.normalize('NFKD', raw.casefold())
                              if not unicodedata.combining(ch))
                mapped.setdefault(key, raw.title() if title else raw)
        return sorted(mapped.values(), key=str.casefold)
    species = labels('species', title=True)
    articles = labels('article')
    varieties = labels('variety')
    campaign, source = inferred_lot_campaign(prod, grafts, deliveries)
    return {'lot_code': code, 'lot_refs': refs, 'graft_refs': graft_refs,
            'species': species, 'articles': articles, 'varieties': varieties,
            'species_label': species[0] if len(species)==1 else ('Plusieurs espèces' if species else 'Non renseignée'),
            'article_label': articles[0] if len(articles)==1 else ('Plusieurs articles' if articles else (varieties[0] if len(varieties)==1 else 'Non renseigné')),
            'campaign': campaign, 'campaign_source': source,
            'production_rows': len(prod), 'delivery_rows': len(deliveries),
            'grafting_rows': len(grafts), 'article_difference_count': mismatches,
            'status': status}


def catalogue():
    """One summary per distinct 5-digit code; original rows never overwritten."""
    _,_,_,pi,di,gi = indexes()
    summaries = [summarize(code,pi[code],di[code],gi[code]) for code in pi.keys()|di.keys()|gi.keys()]
    return sorted(summaries, key=lambda x: (x['species_label'].casefold(), x['article_label'].casefold(), x['lot_code']))


def filtered_catalogue(items, campaign='', species='', article='', search=''):
    """Exact cascade for categories; partial free-text search on lot/ref/article."""
    q = search.strip().casefold()
    def matches(row):
        if campaign == '__UNKNOWN__':
            if row['campaign'] is not None: return False
        elif campaign and row['campaign'] != campaign:
            return False
        if species and species not in row['species'] and not (species == 'Non renseignée' and not row['species']):
            return False
        if article and article not in row['articles'] + row['varieties'] and not (article == 'Non renseigné' and not row['articles'] and not row['varieties']):
            return False
        return not q or any(q in str(v).casefold() for v in
                            [row['lot_code'], *row['lot_refs'], *row['graft_refs'],
                             *row['species'], *row['articles'], *row['varieties']])
    return [row for row in items if matches(row)]


@router.get('/overview')
def overview(campaign: str = Query('', max_length=20),
             species: str = Query('', max_length=120),
             article: str = Query('', max_length=120)):
    """Admin-only historical dashboard totals within the selected lot filters.

    No Excel content is edited. All source links remain five-digit *candidate*
    associations, not proven grafting genealogy or operational stock.
    """
    p, d, g, pi, di, gi = indexes()
    filtered = bool(campaign or species or article)
    if filtered:
        selected_codes = {row['lot_code'] for row in
                          filtered_catalogue(catalogue(), campaign, species, article)}
    else:
        selected_codes = set(pi) | set(di) | set(gi)
    p_codes, d_codes, g_codes = set(pi) & selected_codes, set(di) & selected_codes, set(gi) & selected_codes
    return {'production_rows': sum(len(pi[c]) for c in p_codes),
            'delivery_rows': sum(len(di[c]) for c in d_codes),
            'grafting_rows': sum(len(gi[c]) for c in g_codes),
            'production_lots': len(p_codes), 'grafting_lots': len(g_codes),
            'production_grafting_shared_lots': len(p_codes & g_codes),
            'linked_lots': len(p_codes & d_codes),
            'delivery_lines_linked': sum(len(di[c]) for c in p_codes & d_codes),
            'unlinked_delivery_lines': sum(len(di[c]) for c in d_codes - p_codes),
            'scoped_lots': len(selected_codes), 'filtered': filtered,
            'source_mode': os.getenv('HISTORY_MODE', 'excel').lower(),
            'link_rule': 'LOT / Lot_Production / N° Lot : code commun à cinq chiffres',
            'certification': 'DONNEES_HISTORIQUES_NON_CERTIFIEES'}


@router.get('/filters')
def filters(campaign: str = Query('', max_length=20), species: str = Query('', max_length=120)):
    items = catalogue()
    scoped = filtered_catalogue(items, campaign=campaign)
    if species:
        scoped = filtered_catalogue(scoped, species=species)
    campaigns = sorted({x['campaign'] for x in items if x['campaign']}, reverse=True)
    species_values = sorted({name for row in filtered_catalogue(items, campaign=campaign)
                             for name in (row['species'] or ['Non renseignée'])}, key=str.casefold)
    # Offer BOTH article and variety names, rather than hiding varieties when an article exists.
    articles = sorted({name for row in scoped for name in (row['articles'] + row['varieties'] or ['Non renseigné'])}, key=str.casefold)
    return {'campaigns': [{'value': c, 'label': f'Campagne {c[1:]} · {campaign_bounds(c)[0].strftime("%d/%m/%Y")} – {campaign_bounds(c)[1].strftime("%d/%m/%Y")}'} for c in campaigns],
            'unknown_campaigns': sum(x['campaign'] is None for x in items),
            'species': species_values, 'articles': articles}


@router.get('/lots')
def list_lots(search: str = Query('', max_length=100), campaign: str = Query('', max_length=20),
              species: str = Query('', max_length=120), article: str = Query('', max_length=120),
              limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = filtered_catalogue(catalogue(), campaign, species, article, search)
    return {'total': len(rows), 'items': rows[offset:offset+limit], 'limit': limit, 'offset': offset}


def safe_production(p):
    return {k:p.get(k) for k in ('source_row','lot_ref','lot_code','species','article','variety','seed_lot_ref',
        'production_site_or_depot','sowing_date','germination_date_out','seeds_sown',
        'trays_net','plants_net','trays_delivered_summary','plants_delivered_summary','tray_capacity')}


def safe_delivery(d, article_keys):
    output = {k:d.get(k) for k in ('source_row','lot_ref_delivery','lot_code','type','article','client',
        'document_date','delivery_note_number','tray_quantity','item_quantity','unit',
        'transporter','depot','destination_city','destination_governorate','campaign')}
    output['article_matches_production'] = d.get('article_key') in article_keys if article_keys else None
    return output


def safe_grafting(g):
    return {k:g.get(k) for k in ('source_row','lot_ref','lot_code','lot_production','article','species',
        'variety','greenhouse','grafting_type','seed_lot_ref','ds_reel_source','validated_on',
        'grafting_rate_pct','grafting_loss_pct','total_loss_pct','grafted_trays_gross',
        'grafted_trays_net','plants_gross','plants_net','plants_delivered','plants_destroyed',
        'tray_capacity','status_validated')}


@router.get('/lots/{lot_code}')
def detail(lot_code: str):
    code = lot_five_digits(lot_code)
    if not code:
        raise HTTPException(422, 'Identifiant invalide : code à 5 chiffres requis.')
    _,_,_,pi,di,gi = indexes()
    prod, deliveries, grafts = pi[code],di[code],gi[code]
    if not (prod or deliveries or grafts):
        raise HTTPException(404, 'Aucune information pour ce lot.')
    summary = summarize(code,prod,deliveries,grafts)
    warnings = []
    if len(summary['lot_refs'])>1:
        warnings.append('Plusieurs références de production partagent ce numéro : vérification humaine recommandée.')
    if summary['article_difference_count']:
        warnings.append('Articles différents entre production et livraison ; rapprochement conservé par code de lot.')
    if prod and grafts:
        warnings.append('Lien production ↔ greffage fondé sur le code à 5 chiffres ; relation agronomique à confirmer.')
    if summary['campaign_source'] == 'dates_contradictoires':
        warnings.append('Plusieurs campagnes sont possibles selon les dates sources ; classification à vérifier.')
    elif summary['campaign_source'] == 'date_absente':
        warnings.append('Campagne indéterminée : aucune date source exploitable.')
    if not prod:
        warnings.append('Aucune production franc trouvée pour ce code.')
    if not deliveries:
        warnings.append('Aucune ligne de livraison trouvée pour ce code.')
    article_keys = {p.get('article_key') for p in prod if p.get('article_key')}
    # Decisions are overlays attached to archive rows; they never rewrite Excel sources.
    decisions = {}
    if os.getenv('HISTORY_MODE','excel').lower()=='atlas':
        from app.main import db
        if db is not None:
            for item in db.historical_match_decisions.find({'lotCode':code}):
                decisions[item['deliveryRecordId']] = {
                    'decision': item.get('decision'),
                    'production_record_id': item.get('productionRecordId'),
                    'reason': item.get('reason'),
                    'reviewed_at': item.get('reviewedAt').isoformat() if item.get('reviewedAt') else None,
                }
    delivery_views=[]
    for item in deliveries:
        view=safe_delivery(item, article_keys)
        view['manual_review']=decisions.get(str(item['_id']))
        delivery_views.append(view)
    return {'summary': summary, 'production': [safe_production(p) for p in prod],
            'grafting': [safe_grafting(g) for g in grafts],
            'deliveries': delivery_views,
            'warnings': warnings,
            'note': ('Archives Excel importées dans MongoDB Atlas ; rapprochements de lots à vérifier.'
                     if os.getenv('HISTORY_MODE','excel').lower()=='atlas' else
                     'Trois fichiers Excel consultés en lecture seule ; liens historiques à vérifier.')}
