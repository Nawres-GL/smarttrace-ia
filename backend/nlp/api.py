"""Authenticated read-only NLP interpretation with manual editing handoff.

Interpretation NEVER performs an operation. It may authorize opening a blank or
partially filled editor; the existing operation endpoints remain authoritative.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.auth import authenticated_user
from nlp.service import parse_draft

router = APIRouter(prefix='/api/nlp', tags=['Assistant NLP'])
ROLE_ACTIONS = {
    'production': {'seed', 'sowing', 'germination', 'transfer', 'loss', 'treatment', 'graft'},
    'qualite': {'quality'},
    'logistique': {'preparation', 'delivery', 'return'},
    'admin': {'seed', 'sowing', 'germination', 'transfer', 'loss', 'treatment',
              'graft', 'quality', 'preparation', 'delivery', 'return'},
}
# Negative, question and multi-operation instructions must be rewritten as an
# affirmative statement of ONE completed operation before a form can be opened.
BLOCKING_FLAGS = {
    'NEGATION_OU_ANNULATION', 'QUESTION_OU_DEMANDE_EXPLICATION',
    'OPERATIONS_MULTIPLES_POSSIBLES',
}


class InterpretRequest(BaseModel):
    text: str = Field(min_length=12, max_length=1500)
    context_lot_id: str | None = None


def lot_number(value: str | None):
    match = re.search(r'(?<!\d)(\d{5})(?!\d)', value or '')
    return match.group(1) if match else None


@router.post('/interpret')
def interpret(body: InterpretRequest, request: Request, user=Depends(authenticated_user)):
    role = user['role']
    allowed = ROLE_ACTIONS.get(role)
    if not allowed:
        raise HTTPException(403, 'Assistant réservé aux agents habilités.')

    draft = parse_draft(body.text)
    draft['warnings'] = list(draft.get('warnings', []))
    draft['allowed_actions'] = sorted(allowed)
    draft['review_flags'] = list(draft.get('review_flags', []))
    hard_block = bool(BLOCKING_FLAGS.intersection(draft['review_flags']))

    predicted_action = draft.get('action')
    if predicted_action and predicted_action not in allowed:
        draft['warnings'].append(
            'Votre rôle ne permet pas cette opération. Sélectionnez une opération autorisée, '
            'ou contactez un responsable.'
        )

    # Only resolve operational lots within the authenticated user's sites.
    # Historical Excel references are hints, NEVER stock authorization.
    db = request.app.state.db
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis pour consulter les lots actifs.')
    visible = {} if role == 'admin' else {'siteCode': {'$in': user.get('siteCodes', [])}}
    selected = None
    if body.context_lot_id:
        selected = db.production_lots.find_one(
            {'_id': body.context_lot_id, **visible},
            {'_id': 1, 'code': 1, 'siteCode': 1},
        )
        if not selected:
            draft['warnings'].append('Lot de contexte introuvable ou non autorisé.')

    lot_ref = draft.get('lot_reference')
    candidates = []
    if lot_ref:
        candidates = list(db.production_lots.find(
            {'code': lot_ref, **visible},
            {'_id': 1, 'code': 1, 'siteCode': 1},
        ).limit(5))
        if not candidates:
            five = lot_number(lot_ref)
            if five:
                candidates = list(db.production_lots.find(
                    {'historicalLotCode': five, **visible},
                    {'_id': 1, 'code': 1, 'siteCode': 1},
                ).limit(6))

    if lot_ref and not candidates:
        selected = None
        draft['warnings'].append(
            'Lot cité non trouvé parmi vos lots opérationnels. '
            'Vous pourrez choisir un lot actif dans le formulaire ; un lot Excel seul ne suffit pas.'
        )
    elif len(candidates) == 1:
        if selected and selected['_id'] != candidates[0]['_id']:
            selected = None
            draft['warnings'].append(
                'Le lot cité ne correspond pas au lot de contexte. Sélection manuelle obligatoire.'
            )
        else:
            selected = candidates[0]
    elif len(candidates) > 1:
        selected = None
        draft['warnings'].append(
            'Plusieurs lots actifs correspondent à cette référence. Choisissez le bon lot dans le formulaire.'
        )

    draft['lot_id'] = selected['_id'] if selected else None
    draft['lot_candidates'] = [
        {'id': lot['_id'], 'code': lot['code'], 'site_code': lot['siteCode']}
        for lot in candidates[:5]
    ]

    # Key distinction: *opening an editor* != *authorizing an operation*.
    # Soft neural-model disagreement, unresolved lots and missing fields may be
    # manually corrected. Hard textual risk still blocks the handoff.
    draft['can_open_editor'] = not hard_block
    draft['ready_for_review'] = bool(not hard_block and predicted_action in allowed)
    draft['manual_action_selection_required'] = predicted_action not in allowed
    draft['requires_lot_selection'] = bool(
        predicted_action not in (None, 'seed', 'sowing') and not selected
    )
    draft['needs_manual_completion'] = bool(
        draft.get('missing') or draft['requires_lot_selection'] or
        draft.get('review_required') or draft['manual_action_selection_required']
    )
    draft['disclaimer'] = (
        'Brouillon modifiable uniquement. Aucune opération ni validation de stock '
        'n’est effectuée par l’assistant NLP.'
    )
    return draft
