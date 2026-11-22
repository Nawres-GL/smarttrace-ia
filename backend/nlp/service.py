"""V4 CamemBERT + deterministic parser -> reviewable draft, NEVER a DB write.

Only validated suggestions are used. Unsafe negations or multi-actions are
blocked at API handoff; model disagreement is visible for human correction.
"""
from __future__ import annotations

import os
import re

from nlp.rules import ACTION, REQUIRED, _date, extract
from nlp.safety_guard import assess_instruction


def _threshold(key: str, default: float = 0.45) -> float:
    try:
        value = float(os.getenv(key, str(default)))
        return value if 0 <= value <= 1 else default
    except (ValueError, TypeError):
        return default


def _identifier(text: str) -> str:
    """Trim sentence-final punctuation, but never alter raw NER offsets."""
    return text.strip().rstrip('.,;!?').strip()


def _location(text: str) -> str | None:
    """Only known facility *formats* are safely normalized to backend CODE.

    A real location must still be checked against the selected lot's stock.
    Named locations do not prove they exist in Royal Plants facilities.
    """
    value = _identifier(text)
    match = re.fullmatch(
        r'(chambre|serre|tunnel|zone)\s*(?:n[°o]\s*)?[#-]?(\d{1,3})',
        value, re.IGNORECASE,
    )
    if match:
        return f'{match[1].upper()}-{int(match[2]):02d}'
    match = re.fullmatch(
        r'(chambre|serre|tunnel|zone)\s+(nord|sud|est|ouest|froide|principale|[a-z])',
        value, re.IGNORECASE,
    )
    return f'{match[1].upper()}_{match[2].upper()}' if match else None


def _quantity(value: str) -> int | None:
    clean = re.sub(r'[\s\u202f\u00a0]', '', value.strip())
    number = int(clean) if clean.isdecimal() else 0
    return number if 0 < number <= 1_000_000 else None


def _fill_from_ner(draft: dict, item: dict) -> None:
    """Only fill missing fields, never override a correctly parsed value."""
    label = str(item.get('label', ''))
    raw = _identifier(str(item.get('text', '')))
    action, fields = draft['action'], draft['fields']

    if label == 'LOT':
        if not draft.get('lot_reference') and re.fullmatch(
            r'(?:RO-\d{5}/\d{2}|GRO-G\d{5}/?|\d{5}|RP-[A-Z0-9-]{5,60})',
            raw, re.IGNORECASE,
        ):
            draft['lot_reference'] = raw
        return

    if label == 'QUANTITY':
        target = {'seed': 'quantity_received', 'sowing': 'quantity_sown',
                  'graft': 'quantity_used', 'quality': 'inspected_quantity'}.get(action, 'quantity')
        number = _quantity(raw)
        if number is not None:
            fields.setdefault(target, number)
        return

    if label in ('ORIGIN', 'DESTINATION', 'LOCATION'):
        if action == 'transfer' and label == 'LOCATION':
            return  # No direction information; origin/destination must be explicit.
        if action != 'transfer' and label in ('ORIGIN', 'DESTINATION'):
            return
        normalized = _location(raw)
        if normalized:
            fields.setdefault(label.lower(), normalized)
        return

    if label in ('TEMPERATURE', 'HUMIDITY', 'DURATION') and action == 'germination':
        match = re.search(r'-?\d+(?:[.,]\d+)?', raw)
        if not match:
            return
        number = float(match.group().replace(',', '.'))
        target = {'TEMPERATURE': 'temperature', 'HUMIDITY': 'humidity',
                  'DURATION': 'duration_hours'}[label]
        # Follow operational schema limits; these are not agronomic targets.
        valid = (-20 <= number <= 70 if target == 'temperature' else
                 0 <= number <= 100 if target == 'humidity' else
                 0 <= number <= 2000)
        if valid:
            fields.setdefault(target, number)
        return

    if label == 'DATE':
        target = {'seed': 'received_on', 'sowing': 'sown_on',
                  'germination': 'observed_on', 'treatment': 'performed_on',
                  'graft': 'grafted_on', 'quality': 'inspected_on',
                  'delivery': 'delivered_on', 'return': 'returned_on'}.get(action)
        parsed = _date(raw) if target else None
        if parsed:
            fields.setdefault(target, parsed)
        return

    if label == 'TRAY' and action == 'sowing':
        match = re.fullmatch(r'(?:plateau\s+)?(P\d{1,4})', raw, re.IGNORECASE)
        if match:
            fields.setdefault('tray_type', match[1].upper())
        return

    if label == 'DELIVERY_NOTE' and action == 'delivery':
        if re.fullmatch(r'BL[-_A-Z0-9/]{2,50}', raw, re.IGNORECASE):
            fields.setdefault('delivery_note', raw)
        return

    if label == 'SUPPLIER' and action == 'seed' and 2 <= len(raw) <= 120:
        fields.setdefault('supplier', raw)
        return
    if label == 'VARIETY' and action == 'seed' and 2 <= len(raw) <= 120:
        # Species is a separate field and must be selected/verified manually.
        fields.setdefault('variety', raw)
        return

    if label == 'PRODUCT' and action == 'treatment' and len(raw) <= 120:
        fields.setdefault('product', raw)
        return
    if label == 'CLIENT' and action == 'preparation' and len(raw) <= 120:
        fields.setdefault('client', raw)
        return

    if label == 'ROOTSTOCK_LOT' and action == 'graft':
        draft['warnings'].append(
            'Porte-greffe cité : choisissez le lot actif autorisé dans le formulaire.'
        )
        return

    if label in ('SANITARY', 'HOMOGENEITY') and action == 'quality':
        # These are statuses, not authorization to approve a lot.
        normalized = raw.upper().replace('É', 'E').replace('È', 'E').replace(' ', '_')
        target = 'sanitary_status' if label == 'SANITARY' else 'homogeneity'
        allowed = {'sanitary_status': {'SAIN', 'A_SURVEILLER', 'NON_CONFORME'},
                   'homogeneity': {'HOMOGENE', 'HETEROGENE', 'A_VERIFIER'}}[target]
        if normalized in allowed:
            fields.setdefault(target, normalized)


def _structured_identifier_fallback(draft: dict, text: str) -> None:
    """Recognize explicit BL codes for delivery when NER mislabels them.

    This does NOT accept a rootstock lot as a delivery note; the field is
    restricted to an explicit BL-shaped code in a delivery context.
    """
    if draft['action'] != 'delivery':
        return
    matches = re.findall(r'(?<![A-Za-z0-9])BL[-_][A-Za-z0-9][A-Za-z0-9/_-]{1,50}', text, re.IGNORECASE)
    if len(matches) == 1:
        draft['fields'].setdefault('delivery_note', _identifier(matches[0]))
    elif len(matches) > 1:
        draft['review_required'] = True
        draft['warnings'].append('Plusieurs bons de livraison cités : précisez le document.')


def parse_draft(text: str) -> dict:
    draft = extract(text)
    draft['review_required'] = False
    review = assess_instruction(text)
    draft['review_flags'] = review['reasons']
    if review['status'] == 'REQUIRES_REVIEW':
        draft['review_required'] = True
        draft['warnings'].append(
            'Négation, question ou plusieurs opérations possibles : reformulez en une opération affirmative.'
        )

    _structured_identifier_fallback(draft, text)
    if os.getenv('NLP_MODE', 'rules').lower() != 'hybrid':
        return draft

    try:
        from nlp.transformer import predict
        model = predict(text)
    except (ImportError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        draft['warnings'].append(
            'Modèles CamemBERT indisponibles : extraction locale de secours.'
        )
        return draft

    draft['engine'] = 'camembert-hybrid'
    draft['transformer_intent'] = model['intent']
    draft['transformer_intent_score'] = float(model['intent_score'])
    draft['transformer_alternatives'] = model.get('intent_alternatives', [])
    draft['transformer_entities'] = model.get('entities', [])
    intent_min = _threshold('NLP_MIN_INTENT_SCORE')
    entity_min = _threshold('NLP_MIN_ENTITY_SCORE')
    draft['nlp_thresholds'] = {'intent': intent_min, 'entity': entity_min}

    if model['intent_score'] < intent_min:
        draft['warnings'].append(
            f'Intention CamemBERT sous le seuil {intent_min:.2f} : extraction locale uniquement.'
        )
        if draft.get('intent') and model['intent'] not in (draft['intent'], 'HORS_SUJET'):
            draft['review_required'] = True
            draft['warnings'].append('Désaccord de classement : reformulez avant de continuer.')
        return draft

    if model['intent'] == 'HORS_SUJET':
        draft.update(intent=None, action=None, missing=[])
        draft['review_required'] = True
        draft['warnings'].append('Le classificateur ne reconnaît pas une opération exploitable.')
        return draft

    if draft.get('intent') and draft['intent'] != model['intent']:
        draft['review_required'] = True
        draft['warnings'].append('Désaccord entre règles et CamemBERT : reformulez la demande.')
        # Keep the heuristic guess and conflict warning; the API permits only
        # an explicitly reviewed, editable draft (never submission).
        return draft

    draft['intent'] = model['intent']
    draft['action'] = ACTION[model['intent']]

    for item in model.get('entities', []):
        if float(item.get('score', 0)) >= entity_min:
            _fill_from_ner(draft, item)

    _structured_identifier_fallback(draft, text)
    draft['missing'] = [name for name in REQUIRED[draft['action']]
                        if name not in draft['fields']]
    # Never infer approval, authorization, or inventory updates from NER alone.
    return draft
