"""Explain factual results to employees, leaving technical plan details collapsed in UI."""
from __future__ import annotations
from .catalog import CATALOG, FILTER_LABELS


def _scoped_label(spec, filters: dict) -> str:
    """Translate selected filters into readable French without exposing field names."""
    items = []
    for key, value in filters.items():
        label = FILTER_LABELS.get(key, key)
        items.append(f'{label.lower()} : {"à contrôler" if value == "__PENDING_QUALITY__" else "non conforme" if value == "__NOT_CONFORME__" else value}')
    return ' · '.join(items)


def present_explore(result: dict, dataset: str, metric: str, filters: dict,
                    *, notice: str = '') -> dict:
    """Attach a brief answer, data table and provenance without modifying values.

    Numeric calculations remain exclusively in explorer.explore(). This function
    is PRESENTATION only: it is not an LLM and does not invent statistics.
    """
    spec = CATALOG[dataset]
    met = spec.metrics[metric]
    meta = result.get('meta', {})
    count = meta.get('total_groups', 0)
    rows = result.get('data_rows', [])
    notes = result.get('warnings', [])
    filters_readable = _scoped_label(spec, filters)
    label = met.label
    if count == 0:
        if meta.get('complete_scan', False):
            message = f'Aucune donnée exploitable pour « {label.lower()} » dans {spec.label.lower()}.'
        else:
            message = ('La recherche a atteint la limite de lecture sans trouver de résultat. '
                       'Ce n’est pas une conclusion exhaustive.')
        if filters_readable:
            message += f' Filtres : {filters_readable}.'
        summary = (notice + '\n' if notice else '') + message
    elif meta.get('group_by') is None and len(rows) == 1:
        summary = f'{label} : {rows[0]["display"]}.'
        if filters_readable:
            summary += f' {filters_readable}.'
        if notice:
            summary = notice + '\n' + summary
    else:
        summary = (f'{count} résultat(s) pour « {label.lower()} » dans {spec.label.lower()}.'
                   f' Voici les {len(rows)} premiers affichés.')
        if filters_readable:
            summary += f' {filters_readable}.'
        if notice:
            summary = notice + '\n' + summary
    result.update({
        'answer': summary,
        'summary': summary,
        'status': 'ok' if count else ('incomplete' if not meta.get('complete_scan', False) else 'no_data'),
        'table': {'columns': ['Catégorie', label, 'Lignes prises en compte'],
                  'rows': [{'category': r['label'], 'value': r['display'],
                            'records': r['valid'], 'source_index': r['source_index']}
                           for r in rows]},
        'provenance': {'source': ('Excel historique · non certifié' if spec.historical
                                   else 'MongoDB opérationnel'),
                       'metric': label,
                       'filters': filters_readable,
                       'method': met.description,
                       'complete': meta.get('complete_scan', False)},
        'warnings': notes,
    })
    return result


def present_document(answer: str, sources: list[dict], mode: str,
                     warnings: list[str] | None = None) -> dict:
    """Use a short explanatory response and keep quoted evidence separately."""
    return {'answer': answer, 'summary': answer, 'sources': sources, 'warnings': warnings or [],
            'route': 'documents', 'retrieval_mode': mode, 'generation_mode': 'documents',
            'status': 'ok' if sources else 'no_data', 'read_only': True}
