"""Safe source fallback: comparable measures only; never silently merge history with live records."""
from __future__ import annotations
from dataclasses import replace
from .catalog import CATALOG
from .planner import Plan, norm

# Comparability is explicit: e.g. an operational stock loss ratio is NOT
# the same as the historical Excel graft-loss percentage.
EQUIVALENT = {
    ('operational_lots', 'records'): ('historical_production', 'records'),
    ('operational_lots', 'lots'): ('historical_production', 'lots'),
    ('operational_lots', 'sown'): ('historical_production', 'sown'),
    ('operational_deliveries', 'records'): ('historical_deliveries', 'delivery_notes'),
    ('operational_deliveries', 'quantity'): ('historical_deliveries', 'item_quantity'),
    ('operational_germination', 'germination_rate'): ('historical_production', 'germination_rate'),
}
# Similar topic, but measurements are NOT interchangeable.
RELATED_DIFFERENT = {
    ('operational_lots', 'loss_rate'): ('historical_grafting', 'total_loss_rate'),
}



def explicitly_operational(question: str) -> bool:
    """Return True for requests explicitly restricted to current, live records."""
    q = norm(question)
    return any(word in q for word in (
        'operationnel', 'mongo', 'en cours', 'actuel', 'aujourd hui', 'temps reel',
        'lots actifs', 'production active', 'en stock maintenant',
    ))


def alternative_for_empty(plan: Plan, question: str, user: dict) -> Plan | None:
    """Offer admin-only historical alternative when a comparable operational query is empty.

    Historical and operational facts are never joined or added together; the
    returned plan points to a different clearly labeled source.
    """
    if user.get('role') != 'admin' or explicitly_operational(question):
        return None
    pair = EQUIVALENT.get((plan.dataset, plan.metric)) or RELATED_DIFFERENT.get((plan.dataset, plan.metric))
    if not pair:
        return None
    dataset, metric = pair
    spec = CATALOG[dataset]
    filters = {k: v for k, v in plan.filters.items() if k in spec.dimensions}
    group = plan.group_by if plan.group_by in spec.dimensions else None
    # There is no proven physical genealogy; keep metric semantics explicit.
    return replace(plan, dataset=dataset, metric=metric, group_by=group,
                   filters=filters, extra_groups=tuple(g for g in plan.extra_groups
                                                        if g in spec.dimensions),
                   reason='Source historique de remplacement, non certifiée')


def fallback_notice(original: Plan, replacement: Plan) -> str:
    """Human-facing explanation that a distinct historical source was used."""
    if (original.dataset, original.metric) in RELATED_DIFFERENT:
        return ('Aucun ratio de perte opérationnel exploitable. Le tableau suivant présente '
                'une mesure DIFFÉRENTE : Perte_Totale déclarée sur les lignes Excel de '
                'production greffée, non certifiées. Ces deux taux ne sont pas comparables.')
    if original.dataset == 'operational_deliveries' and original.metric == 'records':
        return ('Aucune livraison opérationnelle accessible. La source historique '
                'compte les numéros de bons distincts, pas les lignes Excel, '
                'et peut inclure différents types de documents.')
    if original.metric == 'quantity':
        return ('Aucune livraison opérationnelle accessible. Voici les lignes de livraison '
                'historiques disponibles, avec leurs unités d’origine (non converties).')
    if original.metric == 'germination_rate':
        return ('Aucun taux de germination opérationnel exploitable. Voici les taux '
                'déclarés dans le fichier Excel historique, qui constituent une mesure différente.')
    return ('Aucune donnée opérationnelle correspondante. Résultats issus des fichiers '
            'Excel historiques, non certifiés, présentés séparément.')
