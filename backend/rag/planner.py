"""Conservative French natural-language -> allowlisted analytical plan.

This is an interpretable parser, not a promise to understand every question.
For unusual questions users can open the structured Data Explorer instead.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from .catalog import CATALOG


def norm(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s.lower())
                   if not unicodedata.combining(c))


@dataclass
class Plan:
    dataset: str
    metric: str
    group_by: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    order: str = 'desc'
    threshold: float | None = None
    limit: int = 10
    reason: str = 'analyse statistique'
    extra_groups: tuple[str, ...] = ()


def _has(s, *words):
    return any(w in s for w in words)


def _group(q: str):
    # Avoid ordinary 'par' phrases such as 'par exemple'.
    for words, key in (
        (('par variete','par varietes','des varietes','les varietes','selon les varietes','quelle variete','quelles varietes'), 'variety'),
        (('par espece','par especes','selon les especes','quelles especes'), 'species'),
        (('par article','par articles','quels articles'), 'article'),
        (('par client','par clients','quels clients','quel client'), 'client'),
        (('par ville','par destination','quelles villes'), 'city'),
        (('par gouvernorat','par gouvernorats'), 'governorate'),
        (('par campagne','par campagnes'), 'campaign'),
        (('par site','par sites'), 'site'),
        (('par mois','chaque mois','mensuel'), 'month'),
        (("par type d'operation", 'par type d operation', 'par type d evenement','par operation','par operations'), 'event_type'),
        (('par statut','par etat','par etape'), 'status'),
        (('par unite','par unites'), 'unit'),
        (('par lot','par lots','quels lots','quel lot','classement des lots'), 'lot_code'),
    ):
        if _has(q, *words):
            return key
    return None


def _filters(question: str, q: str):
    data = {}
    match = re.search(r'\bC\d{2}\b', question, re.IGNORECASE)
    if match:
        data['campaign'] = match.group().upper()
    # Common crop names; novel species can always be entered explicitly in Explorer.
    for crop in ('tomate','pasteque','concombre','courgette','poivron','piment',
                 'aubergine','melon','laitue','chou','fraise','citrouille'):
        if re.search(r'\b'+crop+r's?\b', q):
            data['species'] = crop
            break
    explicit = re.search(r'\bespece\s*[:=]\s*([^,.;?]{2,40})', q)
    if explicit:
        data['species'] = explicit.group(1).strip()
    for key, label in (('client','client'),('variety','variete'),('article','article'),
                       ('city','ville'),('site','site')):
        m = re.search(r'\b'+label+r'\s*[:=]\s*([^,.;?]{2,55})',question,re.IGNORECASE)
        if m:
            data[key] = m.group(1).strip()
    return data


def maybe_plan(question: str, role: str) -> Plan | None:
    q = norm(question)
    # Questions about *how* an operation works belong to document retrieval.
    if (_has(q, 'comment ', 'pourquoi ', 'procedure', 'etapes', 'etape du', 'definition',
             'expliquer', 'explique ', 'regle ', 'certification') and
            not _has(q,'combien','nombre de','taux de','statist','moyenne','classement')):
        return None
    if not _has(q, 'lot', 'perte', 'semis', 'germin', 'greff', 'livrais', 'commande',
                'prepar', 'client', 'ville', 'article', 'variet', 'espece', 'stock',
                'qualit', 'evenement', 'operation', 'plant', 'production', 'quantit', 'bon', 'retour'):
        return None

    historical = _has(q,'historique', 'historiques', 'excel', 'ancienne production')
    operational = _has(q,'operationnel', 'en cours', 'actif', 'actuels', 'mongo')
    # C25 often refers to Excel historical data, but never redirect non-admin to it.
    prefer_history = historical or (not operational and role == 'admin' and 'c25' in q)

    # A requested rate of grafting is a measured percentage, NOT a count of GREFFAGE events.
    if (_has(q, 'taux de greff', 'taux moyen de greff', 'pourcentage de greffage', 'greffage moyen', 'moyenne de greffage')
            and role == 'admin' and not operational):
        dataset = 'historical_grafting'
    elif (_has(q, 'plants greffes', 'quantite greffee', 'plants greffes nets') and
          role == 'admin' and not operational):
        dataset = 'historical_grafting'
    elif _has(q, 'prepar', 'reserv', 'commande', 'reste a livrer', 'restant a livrer'):
        dataset = 'operational_preparations'
    elif _has(q, 'bon de livraison', 'bons de livraison', 'bl ', 'livrais', 'expedi', 'client', 'ville'):
        # Historical Excel has destination city; operational delivery records do not.
        # An admin asking by city should not receive an ungrouped operational total.
        needs_city = _has(q, 'par ville', 'ou par ville', 'et par ville', 'selon la ville',
                          'par destination', 'par gouvernorat')
        dataset = ('historical_deliveries' if (prefer_history or
                    (role == 'admin' and needs_city and not operational))
                   else 'operational_deliveries')
    elif _has(q, 'greff', 'porte greffe'):
        dataset = 'historical_grafting' if prefer_history else 'operational_events'
    elif _has(q, 'perte totale', 'perte_greffage', 'taux de greffage'):
        dataset = 'historical_grafting' if prefer_history else 'operational_lots'
    elif 'germin' in q and _has(q, 'taux', 'compar', 'moyenne', 'pourcentage'):
        dataset = 'historical_production' if prefer_history else 'operational_germination'
    elif _has(q, 'germin', 'semis', 'semees', 'semences'):
        dataset = 'historical_production' if prefer_history else 'operational_lots'
    elif _has(q, 'evenement', 'operations effectuees', 'journal'):
        dataset = 'operational_events'
    else:
        dataset = 'historical_production' if prefer_history else 'operational_lots'

    spec = CATALOG[dataset]
    group_by = _group(q)
    if group_by is None and (re.search(r'\b(?:\d{1,2}\s+)?varietes\b', q) or
                             ('germin' in q and 'compar' in q)) and _has(q,'germin','taux'):
        group_by = 'variety'
    if group_by is not None and group_by not in spec.dimensions:
        # Never silently answer a 'by city' question with an ungrouped global total.
        return None
    if group_by is None and _has(q,'quels lots','liste des lots', 'les lots ayant', 'lots avec', 'top des lots') and 'lot_code' in spec.dimensions:
        group_by = 'lot_code'

    filters = {k:v for k,v in _filters(question,q).items() if k in spec.dimensions}
    if dataset == 'operational_preparations' and _has(q,'quelles prepar', 'commandes restent', 'preparations restent') and not group_by:
        group_by = 'order'
    if dataset == 'operational_lots' and _has(q,'qualite','controle') and _has(q,'par statut','par etat'):
        group_by = 'quality_status'
    if dataset == 'operational_lots' and _has(q,'qualite','controle') and _has(q,'attend','en attente','non conforme','a recontroler'):
        filters['quality_status'] = ('__PENDING_QUALITY__' if _has(q,'attend','en attente','a recontroler','non controle')
                                     else '__NOT_CONFORME__')
    if dataset == 'operational_events' and _has(q,'greff'):
        filters['event_type'] = 'GREFFAGE'
    if dataset == 'operational_lots' and _has(q,'controle qualite', 'attendent la qualite', 'non conform'):
        # If asked for all pending states, don't filter to a single one.
        if 'non conforme' in q:
            filters['quality_status'] = 'NON_CONFORME'
    if dataset == 'operational_lots' and _has(q,'retour'):
        filters['lot_type'] = 'RETOUR'

    if dataset == 'operational_germination':
        metric = ('germination_rate' if _has(q,'taux','pourcentage','moyenne','compar') else
                  'germinated' if _has(q,'quantite germee','plantules') else 'records')
    elif dataset == 'historical_production':
        if _has(q,'germin', 'taux') and _has(q,'germin'):
            metric = 'germination_rate'
        elif _has(q,'plants net','plants nets','production nette', 'quantite nette'):
            metric = 'plants_net'
        elif _has(q,'seme','semis', 'graines') and _has(q,'combien','quantite','total', 'nombre'):
            metric = 'sown'
        elif _has(q,'lot', 'codes de lot') and _has(q,'nombre', 'combien'):
            metric = 'lots'
        else:
            metric = 'records'
    elif dataset == 'historical_grafting':
        metric = ('grafting_loss_rate' if _has(q,'perte de greffage','pertes de greffage','perte greffage') else
                  'total_loss_rate' if _has(q,'perte totale','taux de perte','pertes') else
                  'grafting_rate' if _has(q,'taux de greff', 'taux moyen de greff', 'reussite de greffage', 'greffage moyen') else
                  'plants_net' if _has(q,'plants greffes','quantite greffee', 'plants nets greffes') else
                  'plants_destroyed' if _has(q,'detruit','destruction') else
                  'lots' if _has(q,'nombre de lots') else 'records')
    elif dataset == 'historical_deliveries':
        metric = ('delivery_notes' if _has(q,'combien de bons','nombre de bons','combien de livraisons','nombre de livraisons','plus de livraisons') else
                  'item_quantity' if _has(q,'quantite','combien de plants','volume','total livre') else
                  'lots' if _has(q,'nombre de lots','combien de lots') else 'records')
    elif dataset == 'operational_preparations':
        metric = ('pending' if _has(q,'reste', 'restant', 'non livr', 'a livrer') else
                  'reserved' if 'reserv' in q else 'delivered' if 'livre' in q else 'records')
    elif dataset == 'operational_deliveries':
        metric = 'quantity' if _has(q,'quantite','combien de plants','nombre de plants','total livre') else 'records'
    elif dataset == 'operational_events':
        metric = 'records'
    else:
        metric = ('loss_rate' if _has(q,'taux de perte', 'ratio de perte') else
                  'lost' if _has(q,'perte', 'plants perdus', 'plantes perdues', 'plus perdu') else
                  'sown' if _has(q,'seme','semis') and _has(q,'quantite','combien','total','nombre') else
                  'stock' if 'stock' in q else
                  'delivered' if 'livre' in q else
                  'reserved' if 'reserv' in q else
                  'lots' if _has(q,'combien de lots','nombre de lots','lots distincts') else 'records')

    threshold = None
    m = re.search(r'(?:superieur(?:e|s|es)?\s+a|plus\s+de|depasse(?:nt)?|>)\s*(\d+(?:[.,]\d+)?)\s*%',q)
    if m and metric in ('loss_rate','total_loss_rate','germination_rate','grafting_rate','grafting_loss_rate'):
        threshold = float(m.group(1).replace(',','.'))
        if group_by is None and 'lot_code' in spec.dimensions:
            group_by = 'lot_code'
    order = 'asc' if _has(q,'plus faibles','moins','pire germination','plus bas') else 'desc'
    mlimit = re.search(r'\b(?:top|premiers?|dernier(?:e|s)?|les)\s*(\d{1,2})\b', q)
    limit = max(1, min(50, int(mlimit.group(1)))) if mlimit else (50 if _has(q,'tous les','toutes les') else 10)

    # If no recognizable analytical intent, don't intercept explanatory/doc questions.
    analytical = _has(q,'combien','nombre','quantite','taux','moyenne','classement','statist','plus',
                      'compar', 'top ', 'total','repart', 'liste', 'quels ', 'quelles ', 'par ville',
                      'par variet', 'par espece', 'par client', 'par site', 'restent')
    if not analytical:
        return None
    if dataset not in CATALOG or metric not in CATALOG[dataset].metrics:
        return None
    other = []
    # 'par client ou par ville' asks for TWO views, not just the first group.
    if group_by == 'client' and 'city' in spec.dimensions and re.search(
            r'(?:client(?:s)?).{0,32}(?:ou|et|ainsi que).{0,12}ville', q):
        other = ['city']
    elif group_by == 'city' and 'client' in spec.dimensions and re.search(
            r'ville.{0,32}(?:ou|et|ainsi que).{0,12}client', q):
        other = ['client']
    return Plan(dataset, metric, group_by, filters, order, threshold, limit,
                reason='Analyse déterministe avec champs autorisés', extra_groups=tuple(other))
