"""Deterministic, read-only evidence retrieval from EXISTING SmartTrace collections.

Never evaluate model-created MongoDB queries. Site constraints are created by the server.
Historical Excel evidence is admin-only, matching app/history.py access policy.
"""
from __future__ import annotations

import re
import unicodedata


def normal(text: str) -> str:
    return ''.join(x for x in unicodedata.normalize('NFKD', text.lower())
                   if not unicodedata.combining(x))


def site_scope(user: dict) -> dict:
    if user.get('role') == 'admin':
        return {}
    return {'siteCode': {'$in': list(user.get('siteCodes', []))}}


def code_from_question(question: str) -> str | None:
    # Accept five-digit codes or RO-xxxxx/yy, including a string immediately after 'lot'.
    match = re.search(r'\b(?:lot\s*(?:n[°o.]\s*)?[:#-]?\s*)?([A-Z]{1,6}-\d{5}/\d{2}|\d{5})\b',
                      question, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def campaign_from_question(question: str) -> str | None:
    match = re.search(r'\bC\d{2}\b', question, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def numbers_5(raw: str | None) -> str | None:
    match = re.search(r'(?<!\d)\d{5}(?!\d)', raw or '')
    return match.group(0) if match else None


def evidence(id: str, kind: str, title: str, excerpt: str, **extra):
    return {'id': id, 'kind': kind, 'title': title, 'excerpt': str(excerpt)[:1000], **extra}


def value(row, key, default='non renseigné'):
    val = row.get(key)
    return default if val in (None, '') else str(val)


def lot_record(row):
    return (
        f"Lot {value(row, 'code')} ; site {value(row, 'siteCode')} ; campagne {value(row, 'campaign')} ; "
        f"variété {value(row, 'variety')} ; état {value(row, 'status')} ; "
        f"semis {value(row, 'quantitySown')} ; stock {value(row, 'plantsInStock')} ; "
        f"pertes cumulées {value(row, 'plantsLost', 0)} ; livrés {value(row, 'plantsDelivered', 0)} ; "
        f"qualité {value(row, 'qualityStatus')}."
    )


def _active_lots(question: str, db, user: dict, code: str):
    filters = site_scope(user)
    five = numbers_5(code)
    criteria = [{'_id': code}, {'code': code}, {'historicalFullRef': code}]
    if five:
        criteria.append({'historicalLotCode': five})
    query = {'$and': [filters, {'$or': criteria}]} if filters else {'$or': criteria}
    rows = list(db.production_lots.find(query, {
        '_id': 1, 'code': 1, 'siteCode': 1, 'campaign': 1, 'status': 1,
        'variety': 1, 'quantitySown': 1, 'plantsInStock': 1,
        'plantsLost': 1, 'plantsDelivered': 1, 'qualityStatus': 1,
    }).limit(8))
    sources = [evidence(f'mongo:lot:{r["_id"]}', 'mongodb', f'Lot opérationnel {r.get("code")}',
                        lot_record(r), lot_id=r['_id']) for r in rows]
    if len(rows) > 1:
        return f'{len(rows)} lots opérationnels autorisés correspondent à {code}. Vérifiez le lot voulu.', sources
    if rows:
        r = rows[0]
        response = f'Voici les informations enregistrées pour {r.get("code")} : {lot_record(r)} [1]'
        if any(word in normal(question) for word in ('historique', 'evenement', 'tracabilite', 'etape')):
            # This is a bounded list of directly attached operational events only;
            # do not imply a complete multi-parent genealogy.
            events = list(db.trace_events.find(
                {'subjectType': 'PRODUCTION_LOT', 'subjectId': r['_id'],
                 'siteCode': r['siteCode']},
                {'_id': 1, 'eventType': 1, 'occurredAt': 1, 'blockchainStatus': 1},
            ).sort('occurredAt', -1).limit(11))
            response += '\nÉvénements directement rattachés (ordre récent d’abord) :'
            for event in events[:10]:
                line = (f"{event.get('occurredAt', 'date inconnue')} : "
                        f"{event.get('eventType', 'type inconnu')} ; "
                        f"Fabric {event.get('blockchainStatus', 'NON_CERTIFIE')}")
                sources.append(evidence(f'mongo:event:{event["_id"]}', 'mongodb',
                                        f'Événement {event.get("eventType")}', line, lot_id=r['_id']))
                response += f'\n[{len(sources)}] {line}'
            if len(events) > 10:
                response += '\nAffichage limité aux 10 événements les plus récents.'
            response += ('\nCette liste ne couvre pas automatiquement les événements de semences '
                         'ou les relations de greffage ; elle ne prouve pas une généalogie complète.')
        return response, sources
    return None, []


def historical_lot(question: str, user: dict, code: str):
    """Read-only exact historical matching. Should ONLY be called by admin."""
    if user.get('role') != 'admin':
        return None, []
    five = numbers_5(code)
    if not five:
        return None, []
    from app.history import indexes, summarize, safe_production, safe_delivery, safe_grafting
    _, _, _, pi, di, gi = indexes()
    prod, deliveries, graft = pi.get(five, []), di.get(five, []), gi.get(five, [])
    if not (prod or deliveries or graft):
        return None, []
    summary = summarize(five, prod, deliveries, graft)
    intro = (f'Historique Excel NON CERTIFIÉ pour le code {five} : '
             f'{len(prod)} lignes de production, {len(graft)} lignes de greffage, '
             f'{len(deliveries)} lignes de livraison. Campagne : {summary.get("campaign") or "indéterminée"}. '
             'Le lien repose uniquement sur le code à 5 chiffres ; il ne prouve pas une généalogie.')
    refs = [evidence(f'excel:summary:{five}', 'excel', f'Synthèse historique {five}', intro)]
    for typ, collection, fields, transform in (
        ('production', prod, ('lot_ref', 'species', 'article', 'seeds_sown', 'plants_net', 'sowing_date'), safe_production),
        ('livraison', deliveries, ('delivery_note_number', 'document_date', 'item_quantity', 'unit'),
         lambda r: safe_delivery(r, set())),
        ('greffage', graft, ('lot_ref', 'grafting_rate_pct', 'plants_net', 'validated_on'), safe_grafting),
    ):
        for r in collection[:12]:
            if len(refs) >= 22:
                break
            cleaned = transform(r)
            line = cleaned.get('source_row', '?')
            body = ', '.join(f'{field}={cleaned[field]}' for field in fields if cleaned.get(field) is not None)
            refs.append(evidence(f'excel:{typ}:{five}:{line}', 'excel',
                                 f'Excel {typ} · lot {five} · ligne {line}', body))
    if (len(prod) > 12 or len(deliveries) > 12 or len(graft) > 12 or
            1 + min(12, len(prod)) + min(12, len(deliveries)) + min(12, len(graft)) > 22):
        intro += ' Attention : liste de sources limitée, consulter le dossier historique pour les lignes restantes.'
    return intro, refs


def _rank_losses(question, db, user):
    scope = site_scope(user)
    campaign = campaign_from_question(question)
    if campaign:
        scope = {**scope, 'campaign': campaign}
    # Hard cap, no claims of completeness if the authorized dataset exceeds the cap.
    threshold = re.search(r'(?:superieur(?:e|s|es)?\s+a|plus\s+de|>)[^\d]{0,5}(\d{1,3})\s*%', normal(question))
    threshold_pct = int(threshold.group(1)) if threshold else None
    projection = {'_id': 1, 'code': 1, 'siteCode': 1, 'campaign': 1,
                  'quantitySown': 1, 'plantsLost': 1, 'variety': 1}
    if threshold_pct is None:
        rows = list(db.production_lots.find(scope, projection).sort('plantsLost', -1).limit(11))
        truncated = len(rows) > 10
        rows = rows[:10]
        rows = [r for r in rows if r.get('plantsLost', 0) > 0]
    else:
        cursor = db.production_lots.find(scope, projection).limit(2001)
        all_rows = list(cursor)
        truncated = len(all_rows) > 2000
        rows = []
        for r in all_rows[:2000]:
            sown = r.get('quantitySown') or 0
            if not isinstance(sown, (int, float)) or sown <= 0:
                continue
            pct = 100 * (r.get('plantsLost', 0) or 0) / sown
            if pct > threshold_pct:
                rows.append((pct, r))
        rows = [r for _, r in sorted(rows, key=lambda x: x[0], reverse=True)[:10]]
    refs = []
    lines = []
    for idx, r in enumerate(rows, 1):
        amount = r.get('plantsLost', 0) or 0
        sown = r.get('quantitySown') or 0
        rate = f' ; ratio pertes/semis {100*amount/sown:.1f} %' if sown and sown > 0 else ''
        line = f'{r.get("code")} ({r.get("siteCode")}) : {amount} plants perdus{rate}'
        lines.append(f'{idx}. {line} [{idx}]')
        refs.append(evidence(f'mongo:lot:{r["_id"]}', 'mongodb', f'Lot {r.get("code")}', line, lot_id=r['_id']))
    if not lines:
        return ('Aucun résultat correspondant dans les lots opérationnels accessibles. '
                'Ce constat ne couvre pas les historiques Excel, qui constituent une source séparée.'), []
    caveat = (' Comparaison partielle : trop de lots pour une analyse exhaustive.' if truncated else '')
    if threshold_pct is not None:
        caveat += ' Le ratio est pertes cumulées divisées par quantité semée ; ce n’est pas un indicateur agronomique officiel.'
    return 'Lots opérationnels accessibles avec pertes :\n' + '\n'.join(lines) + caveat, refs


def _quality_waiting(db, user, campaign):
    match = {**site_scope(user), 'qualityStatus': {'$ne': 'CONFORME'}}
    if campaign:
        match['campaign'] = campaign
    items = list(db.production_lots.find(match,
        {'_id': 1, 'code': 1, 'siteCode': 1, 'qualityStatus': 1, 'status': 1})
                 .limit(11))
    truncated = len(items) > 10
    refs = [evidence(f'mongo:lot:{r["_id"]}', 'mongodb', f'Lot {r.get("code")}',
                     f"Site {r.get('siteCode')}; qualité {r.get('qualityStatus', 'NON_CONTROLE')}", lot_id=r['_id'])
            for r in items[:10]]
    if not refs:
        return 'Aucun lot non conforme ou en attente de contrôle dans les données accessibles.', []
    lines = [f'{i}. {r["title"]} — {r["excerpt"]} [{i}]' for i, r in enumerate(refs, 1)]
    suffix = '\nListe limitée aux 10 premiers résultats.' if truncated else ''
    return 'Lots opérationnels sans statut qualité CONFORME :\n' + '\n'.join(lines) + suffix, refs


def _total_lots(db, user, campaign):
    match = site_scope(user)
    if campaign:
        match['campaign'] = campaign
    number = db.production_lots.count_documents(match)
    qualifier = f' pour la campagne {campaign}' if campaign else ''
    scope = 'tous les sites' if user.get('role') == 'admin' else 'vos sites autorisés'
    statement = f'Nombre de lots opérationnels{qualifier} ({scope}) : {number}.'
    return statement + ' [1]', [evidence(f'mongo:aggregate:lots:{campaign or "all"}', 'mongodb',
                                           'Comptage des lots opérationnels', statement)]



def _pending_preparations(db, user):
    # This collection is site-scoped like production_lots.
    scope = site_scope(user)
    rows = list(db.preparations.find(scope, {
        '_id': 1, 'siteCode': 1, 'lotId': 1, 'orderReference': 1,
        'quantityReserved': 1, 'quantityDelivered': 1,
    }).limit(2001))
    incomplete = len(rows) > 2000
    result = [r for r in rows[:2000]
              if (r.get('quantityReserved') or 0) > (r.get('quantityDelivered') or 0)]
    result.sort(key=lambda r: (r.get('quantityReserved') or 0) - (r.get('quantityDelivered') or 0), reverse=True)
    sources = []
    for r in result[:10]:
        due = (r.get('quantityReserved') or 0) - (r.get('quantityDelivered') or 0)
        line = (f"Préparation {r['_id']} · site {r.get('siteCode')} · "
                f"lot {r.get('lotId')} · commande {r.get('orderReference')} : "
                f'{due} plants encore réservés et non livrés.')
        sources.append(evidence(f'mongo:preparation:{r["_id"]}', 'mongodb',
                                f'Préparation {r.get("orderReference")}', line))
    if not sources:
        return 'Aucune préparation incomplètement livrée n’a été trouvée dans les données accessibles.', []
    answer = 'Préparations avec quantité restant à livrer :\n' + '\n'.join(
        f'[{i}] {s["excerpt"]}' for i, s in enumerate(sources, 1))
    if len(result) > 10 or incomplete:
        answer += '\nListe limitée : elle ne constitue pas un inventaire exhaustif.'
    return answer, sources


def structured_search(question: str, db, user: dict):
    """Returns (answer, sources, route, warnings). Answers are programmatically rendered."""
    q = normal(question)
    campaign = campaign_from_question(question)
    code = code_from_question(question)
    if code:
        msg, source = _active_lots(question, db, user, code)
        if user.get('role') == 'admin':
            try:
                hx, hx_sources = historical_lot(question, user, code)
            except Exception:  # Excel not mounted, malformed, etc; never leak internal paths.
                hx, hx_sources = None, []
            if hx:
                if msg:
                    # Keep each source namespace distinct; never assert historical genealogy.
                    return msg + f'\nHistorique Excel distinct : {hx} [{len(source)+1}]', source + hx_sources, 'lot', []
                return hx + ' [1]', hx_sources, 'historique', []
        if msg:
            return msg, source, 'lot', []
        return (f'Aucun lot opérationnel accessible ne correspond à {code}. '
                + ('Aucune correspondance historique autorisée disponible.' if user.get('role') == 'admin'
                   else 'L’historique Excel n’est pas accessible à votre rôle.'), [], 'lot_absent', [])
    # Germination analytics are sourced ONLY from recorded GERMINATION events.
    # Historical Excel contains an explicit Taux_Germination column. Report
    # that field as non-certified historical data, separate from live events.
    if 'germination' in q and any(x in q for x in ('compar', 'taux', 'variet', 'moyenn', 'statist')):
        from .analytics import operational_germination, historical_reported_germination
        answer, refs, warnings = operational_germination(question, db, user)
        if answer is not None:
            return answer, refs, 'germination', warnings
        if user.get('role') == 'admin':
            try:
                historical, h_sources, h_warnings = historical_reported_germination(question, user)
            except Exception:
                historical, h_sources, h_warnings = None, [], ['Historique Excel indisponible.']
            if historical:
                return ('Aucun événement GERMINATION avec quantités exploitables n’a été trouvé dans les '
                        'lots opérationnels accessibles.\n' + historical), h_sources, 'germination_historique', warnings + h_warnings
        return ('Impossible de comparer les taux de germination pour ce périmètre : aucun événement '
                'GERMINATION accessible avec quantités semées et germées. Les Excel historiques '
                'ne fournissent pas directement le taux de germination; leur consultation est réservée '
                'les administrateurs.'), [], 'germination_indisponible', warnings

    if any(x in q for x in ('perte', 'perdu', 'destruction')) and any(x in q for x in
                        ('lot', 'plus', 'classe', 'taux', 'quant', 'fort')):
        answer, refs = _rank_losses(question, db, user)
        if not refs and user.get('role') == 'admin':
            from .analytics import historical_grafting_losses
            threshold = re.search(r'(?:superieur(?:e|s|es)?\s+a|plus\s+de|>)[^\d]{0,5}(\d{1,3})\s*%', q)
            threshold_pct = int(threshold.group(1)) if threshold else None
            try:
                historical, h_sources, h_warnings = historical_grafting_losses(question, user, threshold_pct)
            except Exception:
                historical, h_sources, h_warnings = None, [], ['Historique Excel indisponible.']
            if historical:
                return (answer + '\n' + historical), h_sources, 'pertes_historiques', h_warnings
            return answer, [], 'pertes', h_warnings
        return answer, refs, 'pertes', []
    if ('qualite' in q or 'controle' in q) and any(x in q for x in
                                                    ('lot', 'attend', 'non conforme', 'en attente')) and not q.startswith('comment'):
        answer, refs = _quality_waiting(db, user, campaign)
        return answer, refs, 'qualite', []
    if ('prepar' in q or 'reserv' in q) and ('livr' in q or 'expedi' in q):
        answer, refs = _pending_preparations(db, user)
        return answer, refs, 'preparations', []
    if ('combien' in q or 'nombre' in q or 'total' in q) and 'lot' in q:
        answer, refs = _total_lots(db, user, campaign)
        return answer, refs, 'comptage', []
    return None, [], 'documents', []
