"""Descriptive historical analytics with explicit source and unit limitations."""
from collections import Counter, defaultdict
from fastapi import APIRouter, Depends, Query
from app.auth import require_role
from app.history import load_historical

router = APIRouter(prefix='/api/insights', tags=['Statistiques et insights'])


def _num(v):
    try:
        return float(v) if v is not None and v != '' else 0.0
    except (TypeError, ValueError):
        return 0.0


def _rank(values, limit=10):
    return [{'label': str(k), 'value': round(v, 2)}
            for k, v in sorted(values.items(), key=lambda t: (-t[1], str(t[0])))[:limit]]


def _campaign(row):
    value = str(row.get('campaign') or '').strip()
    if value:
        return value
    year = row.get('production_year')
    if year:
        return str(year)
    date = str(row.get('document_date') or row.get('sowing_date') or row.get('validated_on') or row.get('ds_reel_source') or '')
    return date[:4] if len(date) >= 4 and date[:4].isdigit() else 'Non renseignée'


def _options(rows, key):
    return sorted({str(r.get(key)).strip() for r in rows if r.get(key) and str(r.get(key)).strip()})


def calculate_historical(p, d, g, campaign='', species='', client='', greenhouse='', unit=''):
    """Filter each applicable dataset; never mix trays, plants and delivery units."""
    all_p, all_d, all_g = p, d, g
    if campaign:
        p = [r for r in p if _campaign(r) == campaign]
        d = [r for r in d if _campaign(r) == campaign]
        g = [r for r in g if _campaign(r) == campaign]
    if species:
        p = [r for r in p if str(r.get('species') or '') == species]
        d = [r for r in d if str(r.get('species') or '') == species]
        g = [r for r in g if str(r.get('species') or '') == species]
    if client:
        d = [r for r in d if str(r.get('client') or '') == client]
        # Customer is not known in production/grafting sources: avoid pretending otherwise.
    if unit:
        d = [r for r in d if str(r.get('unit') or '') == unit]
    if greenhouse:
        g = [r for r in g if str(r.get('greenhouse') or '') == greenhouse]

    production_by_species = defaultdict(float)
    production_by_variety = defaultdict(float)
    prod_rows_by_species = Counter()
    delivery_by_client = defaultdict(float)
    delivery_by_region = defaultdict(float)
    delivery_by_article = defaultdict(float)
    deliveries_by_month = defaultdict(float)
    delivery_document_counts = Counter()
    delivery_lines_by_client = Counter()
    delivery_lines_by_region = Counter()
    delivery_lines_by_unit = Counter()
    graft_rates = defaultdict(list)
    graft_losses = defaultdict(list)
    missing_lot = Counter()
    missing_species = Counter()
    production_lot_refs = defaultdict(set)
    total_seed = total_net = 0
    for r in p:
        sp = r.get('species') or 'Non renseignée'
        variety = r.get('variety') or 'Non renseignée'
        prod_rows_by_species[sp] += 1
        if r.get('seeds_sown') is not None:
            qty = _num(r.get('seeds_sown'))
            production_by_species[sp] += qty
            production_by_variety[variety] += qty
            total_seed += qty
        total_net += _num(r.get('plants_net'))
        if not r.get('lot_code'):
            missing_lot['production'] += 1
        if not r.get('species'):
            missing_species['production'] += 1
        if r.get('lot_code') and r.get('lot_ref'):
            production_lot_refs[str(r['lot_code'])].add(str(r['lot_ref']))
    for r in d:
        # Units may differ by row, so expose raw quantity only with a unit warning.
        client_label = r.get('client') or 'Non renseigné'
        delivery_lines_by_client[client_label] += 1
        delivery_lines_by_region[r.get('destination_governorate') or 'Non renseignée'] += 1
        delivery_lines_by_unit[r.get('unit') or 'Non renseignée'] += 1
        delivery_by_client[client_label] += _num(r.get('item_quantity'))
        delivery_by_region[r.get('destination_governorate') or 'Non renseignée'] += _num(r.get('item_quantity'))
        delivery_by_article[r.get('article') or 'Non renseigné'] += _num(r.get('item_quantity'))
        date = str(r.get('document_date') or '')
        if len(date) >= 7 and date[:4].isdigit() and date[4] == '-' and date[5:7].isdigit():
            deliveries_by_month[date[:7]] += _num(r.get('item_quantity'))
        if r.get('delivery_note_number'):
            delivery_document_counts[str(r['delivery_note_number'])] += 1
        if not r.get('lot_code'):
            missing_lot['livraison'] += 1
        if not r.get('species'):
            missing_species['livraison'] += 1
    for r in g:
        key = r.get('greenhouse') or 'Non renseignée'
        if r.get('grafting_rate_pct') is not None:
            graft_rates[key].append(_num(r['grafting_rate_pct']))
        if r.get('grafting_loss_pct') is not None:
            graft_losses[key].append(_num(r['grafting_loss_pct']))
        if not r.get('lot_code'):
            missing_lot['greffage'] += 1
        if not r.get('species'):
            missing_species['greffage'] += 1
    prod_codes = {str(r['lot_code']) for r in p if r.get('lot_code')}
    unmatched = sum(1 for r in d if r.get('lot_code') and str(r['lot_code']) not in prod_codes)
    ambiguous = sum(1 for refs in production_lot_refs.values() if len(refs) > 1)
    flags = []
    if unmatched:
        flags.append({'title':'Livraisons sans production correspondante', 'count':unmatched,
                      'description':'Code LOT absent de la sélection de production. Un filtre peut aussi expliquer cette absence.'})
    if sum(missing_lot.values()):
        flags.append({'title':'Numéros de lot manquants', 'count':sum(missing_lot.values()),
                      'description':'Lignes impossibles à rapprocher par leur code de lot.'})
    if ambiguous:
        flags.append({'title':'Références LOT ambiguës', 'count':ambiguous,
                      'description':'Plusieurs références de production partagent le même code à cinq chiffres.'})
    rates = [{'label':k, 'value':round(sum(v)/len(v),2), 'sample_size':len(v)}
             for k, v in graft_rates.items() if v]
    rates.sort(key=lambda x:(-x['sample_size'], x['label']))
    losses = [{'label':k, 'value':round(sum(v)/len(v),2), 'sample_size':len(v)}
              for k,v in graft_losses.items() if v]
    losses.sort(key=lambda x:(-x['sample_size'], x['label']))
    return {
        'scope':'historical_excel', 'method':'descriptive_only',
        'filters': {'campaign':campaign,'species':species,'client':client,'greenhouse':greenhouse,'unit':unit},
        'filter_options': {
            'campaigns':sorted({_campaign(r) for r in all_p+all_d+all_g}),
            'species':sorted(set(_options(all_p,'species')+_options(all_d,'species')+_options(all_g,'species'))),
            'clients':_options(all_d,'client'), 'greenhouses':_options(all_g,'greenhouse'),
            'units':_options(all_d,'unit')},
        'kpis': {'production_rows':len(p),'delivery_rows':len(d),'grafting_rows':len(g),
                 'distinct_species':len(prod_rows_by_species),
                 'distinct_lot_codes':len({str(r['lot_code']) for r in p+d+g if r.get('lot_code')}),
                 'production_seeds_sown':round(total_seed,2), 'net_plants_production':round(total_net,2),
                 'delivery_notes':len(delivery_document_counts),
                 'unlinked_delivery_rows':unmatched,'ambiguous_lot_codes':ambiguous,
                 'missing_lot_rows':sum(missing_lot.values()),
                 'missing_species_rows':sum(missing_species.values())},
        'production_by_species':_rank(production_by_species),
        'production_by_variety':_rank(production_by_variety),
        'production_rows_by_species':_rank(prod_rows_by_species),
        'delivery_lines_by_client':_rank(delivery_lines_by_client),
        'delivery_lines_by_region':_rank(delivery_lines_by_region),
        'delivery_lines_by_unit':_rank(delivery_lines_by_unit),
        'delivery_by_client':_rank(delivery_by_client) if unit else [],
        'delivery_by_region':_rank(delivery_by_region) if unit else [],
        'delivery_by_article':_rank(delivery_by_article) if unit else [],
        'monthly_delivery':[{'label':k,'value':round(v,2)} for k,v in sorted(deliveries_by_month.items())][-24:] if unit else [],
        'graft_rate_by_greenhouse':rates[:12],
        'graft_loss_by_greenhouse':losses[:12],
        'alerts':flags,
        'notes':[
            'Statistiques descriptives : aucune prédiction automatique.',
            'Filtres client/serre appliqués uniquement aux fichiers disposant de ces informations.',
            'Les sommes de quantités de livraison ne sont présentées que lorsqu’une unité Excel unique est sélectionnée.',
            'Taux de greffage et de perte : moyennes non pondérées, avec nombre de lignes disponibles.',
            'Correspondance de lot fondée sur un code à cinq chiffres, non une preuve d’identité physique.'
        ]
    }


@router.get('/historique')
def historic_insights(
    campaign: str = Query('',max_length=100),
    species: str = Query('',max_length=100),
    client: str = Query('',max_length=160),
    greenhouse: str = Query('',max_length=100),
    unit: str = Query('',max_length=80),
    user=Depends(require_role('admin')),
):
    p, d, g = load_historical()
    return calculate_historical(p,d,g,campaign=campaign,species=species,client=client,greenhouse=greenhouse,unit=unit)
