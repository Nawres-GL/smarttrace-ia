"""Royal Plants operational workflow for NEW lots only.

Existing Excel sources remain read-only and are never promoted to validated events.
Every state transition and its audit event are in a MongoDB transaction.
This is a pilot domain model: final Royal Plants business rules require field validation.
"""
from __future__ import annotations

import base64
import io
import os
from datetime import date
from typing import Literal
from typing import Annotated
from uuid import uuid4

import qrcode
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from .auth import authenticated_user, database, require_role, require_site
from .ledger import event_public, insert_event, make_event, now, verify_local_integrity
from .campaigns import campaign_for_date
from .unified_registry import register_operational

router = APIRouter(prefix='/api/operations', tags=['Opérations traçables'])

CODE = r'^[A-Za-z0-9_-]{2,35}$'


def serial_lot(lot):
    return {'id': lot['_id'], 'code': lot['code'], 'site_code': lot['siteCode'],
            'species': lot.get('species'), 'article': lot.get('article') or lot.get('variety'),
            'variety': lot.get('variety'), 'campaign': lot.get('campaign') or campaign_for_date(lot.get('sownOn')),
            'seed_lot_id': lot.get('seedLotId'),
            'lot_type': lot.get('lotType', 'SEMIS'), 'parents': lot.get('parentLotIds', []),
            'historical_lot_code': lot.get('historicalLotCode'), 'historical_full_ref': lot.get('historicalFullRef'),
            'status': lot.get('status', 'SEMIS_ENREGISTRE'),
            'quantity_sown': lot.get('quantitySown'), 'plants_in_stock': lot.get('plantsInStock', 0),
            'plants_lost': lot.get('plantsLost', 0), 'plants_delivered': lot.get('plantsDelivered', 0),
            'plants_reserved': lot.get('plantsReserved', 0), 'plants_returned': lot.get('plantsReturned', 0),
            'locations': lot.get('locations', {}), 'reserved_locations': lot.get('reservedLocations', {}),
            'quality_status': lot.get('qualityStatus', 'NON_CONTROLE'),
            'quality_approved': lot.get('qualityApproved', 0), 'revision': lot.get('revision', 0)}


def ensure_lot(db, lot_id, user, session=None):
    lot = db.production_lots.find_one({'_id': lot_id}, session=session)
    if not lot:
        raise HTTPException(404, 'Lot opérationnel introuvable. Les fichiers Excel sont consultables séparément.')
    require_site(user, lot['siteCode'])
    return lot


def guarantee(condition, message, code=422):
    if not condition:
        raise HTTPException(code, message)


def location_available(lot, location):
    return lot.get('locations', {}).get(location, 0) - lot.get('reservedLocations', {}).get(location, 0)


def commit_lot(db, old, changes, session):
    # Optimistic revision + MongoDB transaction detect concurrent conflicting commands.
    updated = db.production_lots.update_one({'_id': old['_id'], **({'revision': old['revision']} if 'revision' in old else {'revision': {'$exists': False}})},
        {'$set': changes, '$inc': {'revision': 1}}, session=session)
    if updated.matched_count != 1:
        raise HTTPException(409, 'Le lot a été modifié par un autre utilisateur. Actualisez puis réessayez.')


def execute(db, lot_id, actor, role, idempotency_key, event_name, handler):
    guarantee(bool(idempotency_key and len(idempotency_key) >= 12), 'Clé de requête manquante ou trop courte.', 400)
    # A command replay returns the original event without applying its stock movement twice.
    existing = db.trace_events.find_one({'idempotencyKey': idempotency_key})
    if existing:
        # Replays must never leak another employee's event or another site's records.
        ensure_lot(db, lot_id, actor)
        guarantee(existing.get('actorId') == actor['_id'], 'Clé enregistrée par un autre utilisateur.', 403)
        guarantee(existing['subjectId'] == lot_id and existing['eventType'] == event_name,
                  'Cette clé de requête a déjà été utilisée pour une autre opération.', 409)
        return {'event': event_public(existing), 'replayed': True}

    def txn(session):
        previous = db.trace_events.find_one({'idempotencyKey': idempotency_key}, session=session)
        if previous:
            ensure_lot(db, lot_id, actor, session)
            guarantee(previous.get('actorId') == actor['_id'], 'Clé réservée à un autre utilisateur.', 403)
            guarantee(previous['subjectId'] == lot_id and previous['eventType'] == event_name,
                      'Clé de requête réutilisée.', 409)
            return {'event': event_public(previous), 'replayed': True}
        old = ensure_lot(db, lot_id, actor, session)
        modifications, details, extra = handler(old, session)
        commit_lot(db, old, modifications, session)
        ev = make_event('PRODUCTION_LOT', lot_id, old['siteCode'], event_name, details, actor['_id'])
        ev['idempotencyKey'] = idempotency_key
        insert_event(db, ev, session)
        return {'event': event_public(ev), 'replayed': False, **(extra or {})}

    try:
        with db.client.start_session() as session:
            return session.with_transaction(txn)
    except DuplicateKeyError:
        prior = db.trace_events.find_one({'idempotencyKey': idempotency_key})
        if prior and prior['subjectId'] == lot_id and prior['eventType'] == event_name:
            ensure_lot(db, lot_id, actor)
            guarantee(prior.get('actorId') == actor['_id'], 'Clé réservée à un autre utilisateur.', 403)
            return {'event': event_public(prior), 'replayed': True}
        raise HTTPException(409, 'Opération déjà enregistrée.')


class GerminationIn(BaseModel):
    quantity: int = Field(ge=0)
    location: str = Field(pattern=CODE)
    temperature: float | None = Field(default=None, ge=-20, le=70)
    humidity: float | None = Field(default=None, ge=0, le=100)
    observed_on: date
    started_on: date
    ended_on: date
    duration_hours: float = Field(ge=0, le=2000)
    notes: str = Field(default='', max_length=2000)


class TransferIn(BaseModel):
    quantity: int = Field(gt=0)
    origin: str = Field(pattern=CODE)
    destination: str = Field(pattern=CODE)
    notes: str = Field(default='', max_length=2000)


class LossIn(BaseModel):
    quantity: int = Field(gt=0)
    location: str = Field(pattern=CODE)
    reason: str = Field(min_length=3, max_length=500)


class TreatmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    intervention_type: Literal['ENTRETIEN', 'TRAITEMENT', 'OBSERVATION']
    location: str = Field(pattern=CODE)
    performed_on: date
    product: str = Field(default='', max_length=120)
    dose: str = Field(default='', max_length=100)
    notes: str = Field(default='', max_length=2000)


class GraftIn(BaseModel):
    rootstock_lot_id: str
    scion_location: str = Field(pattern=CODE)
    rootstock_location: str = Field(pattern=CODE)
    quantity_used: int = Field(gt=0)
    quantity_success: int = Field(ge=0)
    grafted_on: date
    notes: str = Field(default='', max_length=1200)


class QualityIn(BaseModel):
    approved: bool
    inspected_quantity: int = Field(ge=0)
    approved_quantity: int = Field(ge=0)
    sanitary_status: Literal['SAIN', 'A_SURVEILLER', 'NON_CONFORME']
    homogeneity: Literal['HOMOGENE', 'HETEROGENE', 'A_VERIFIER']
    inspected_on: date
    notes: str = Field(min_length=3, max_length=2000)


class PreparationIn(BaseModel):
    client: str = Field(min_length=2, max_length=150)
    order_reference: str = Field(min_length=2, max_length=80)
    quantity: int = Field(gt=0)
    location: str = Field(pattern=CODE)
    trays: int | None = Field(default=None, ge=0)
    pallets: int | None = Field(default=None, ge=0)


class DeliveryIn(BaseModel):
    preparation_id: str
    quantity: int = Field(gt=0)
    delivery_note: str = Field(min_length=2, max_length=100)
    transporter: str = Field(min_length=2, max_length=100)
    vehicle: str = Field(min_length=2, max_length=90)
    received_by: str = Field(min_length=2, max_length=100)
    receipt_confirmed: bool
    delivered_on: date


class ReturnIn(BaseModel):
    preparation_id: str
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    returned_on: date


class CorrectionIn(BaseModel):
    original_event_id: str
    note: str = Field(min_length=5, max_length=1500)


class LegacyBaselineIn(BaseModel):
    lot_code: str = Field(pattern=r'^\d{5}$')
    full_reference: str = Field(min_length=4, max_length=80)
    site_code: str = Field(pattern=CODE)
    stock_counted: int = Field(ge=0)
    location: str = Field(pattern=CODE)
    verified_on: date
    verification_note: str = Field(min_length=10, max_length=1500)


@router.post('/activate-history', status_code=201)
def activate_history(data: LegacyBaselineIn, request: Request,
                     actor=Depends(require_role('admin'))):
    """Start live tracking of an Excel lot from a PHYSICALLY VERIFIED current balance.

    We never treat previous Excel rows as reconstructed operational audit events.
    """
    from app.history import indexes
    db = database(request)
    require_site(actor, data.site_code)
    if db.sites.find_one({'code': data.site_code}) is None:
        raise HTTPException(422, 'Site inconnu.')
    _, _, _, production_index, _, graft_index = indexes()
    records = production_index.get(data.lot_code, []) + graft_index.get(data.lot_code, [])
    eligible = [r for r in records if r.get('lot_ref') == data.full_reference]
    guarantee(bool(eligible), 'Référence de production introuvable pour ce code de lot. Vérifiez les fichiers Excel.')
    existing = db.production_lots.find_one({'historicalFullRef': data.full_reference})
    if existing:
        raise HTTPException(409, 'Ce lot Excel est déjà activé dans SmartTrace.')
    lot_id = str(uuid4())
    row = {'_id': lot_id, 'code': data.full_reference, 'historicalLotCode': data.lot_code,
           'historicalFullRef': data.full_reference, 'siteCode': data.site_code,
           'species': eligible[0].get('species'), 'article': eligible[0].get('article'),
           'variety': eligible[0].get('variety') or eligible[0].get('article') or 'Non précisée',
           'campaign': campaign_for_date(eligible[0].get('sowing_date')),
           'seedLotId': None, 'lotType': 'REPRISE_HISTORIQUE', 'parentLotIds': [],
           'quantitySown': None, 'sownOn': None,
           'plantsInStock': data.stock_counted, 'plantsLost': 0, 'plantsReserved': 0,
           'plantsDelivered': 0, 'plantsReturned': 0, 'qualityApproved': 0,
           'qualityStatus': 'NON_CONTROLE', 'status': 'EN_PRODUCTION',
           'locations': {data.location: data.stock_counted}, 'reservedLocations': {},
           'revision': 0, 'createdAt': now()}
    event = make_event('PRODUCTION_LOT', lot_id, data.site_code, 'OUVERTURE_HISTORIQUE',
            {'reference_excel': data.full_reference, 'code_excel': data.lot_code,
             'stock_reel_verifie': data.stock_counted, 'emplacement': data.location,
             'date_verification': data.verified_on.isoformat(), 'justificatif': data.verification_note,
             'historique_passe_non_verifie': True}, actor['_id'])
    try:
        with db.client.start_session() as session:
            session.with_transaction(lambda tx: (db.production_lots.insert_one(row, session=tx),
                                                 register_operational(db, row, tx),
                                                 insert_event(db, event, tx)))
    except DuplicateKeyError:
        raise HTTPException(409, 'Référence de lot déjà activée.')
    return serial_lot(row)


@router.get('/overview')
def overview(request: Request, user=Depends(authenticated_user)):
    db = database(request)
    match = {} if user['role'] == 'admin' else {'siteCode': {'$in': user.get('siteCodes', [])}}
    return {'lots': db.production_lots.count_documents(match),
            'pending_quality': db.production_lots.count_documents({**match, 'qualityStatus': {'$ne': 'CONFORME'}}),
            'deliveries': db.deliveries.count_documents(match),
            'audit_events': db.trace_events.count_documents(match)}


@router.get('/lots')
def list_active_lots(request: Request, limit: int = Query(200, ge=1, le=500),
                     offset: int = Query(0, ge=0), user=Depends(authenticated_user)):
    db = database(request)
    where = {} if user['role'] == 'admin' else {'siteCode': {'$in': user.get('siteCodes', [])}}
    return [serial_lot(x) for x in db.production_lots.find(where).sort('createdAt', DESCENDING).skip(offset).limit(limit)]


@router.get('/lots/{lot_id}')
def detail(lot_id: str, request: Request, user=Depends(authenticated_user)):
    db = database(request)
    lot = ensure_lot(db, lot_id, user)
    ancestry = list(db.trace_events.find({'$or': [
        {'subjectType': 'PRODUCTION_LOT', 'subjectId': lot_id},
        {'subjectType': 'SEED_LOT', 'subjectId': lot.get('seedLotId')},
        {'details.parent_lot_ids': lot_id},
        {'details.lot_fils_id': lot_id},
    ]}).sort('occurredAtDt', ASCENDING).limit(500))
    preparations = list(db.preparations.find({'lotId': lot_id}).sort('createdAt', DESCENDING))
    return {'lot': serial_lot(lot), 'events': [event_public(x) for x in ancestry],
            'preparations': [{'id': p['_id'], 'client': p['client'], 'order_reference': p['orderReference'],
                              'quantity_reserved': p['quantityReserved'], 'quantity_delivered': p['quantityDelivered'],
                              'quantity_returned': p.get('quantityReturned', 0), 'location': p['location']} for p in preparations]}


@router.get('/lots/{lot_id}/integrity')
def integrity(lot_id: str, request: Request, user=Depends(authenticated_user)):
    db = database(request)
    lot = ensure_lot(db, lot_id, user)
    matching = {'siteCode': lot['siteCode'], '$or': [
        {'subjectType': 'PRODUCTION_LOT', 'subjectId': lot_id},
        {'subjectType': 'SEED_LOT', 'subjectId': lot.get('seedLotId')},
        {'details.parent_lot_ids': lot_id},
        {'details.lot_fils_id': lot_id},
    ]}
    events = list(db.trace_events.find(matching).limit(500))
    invalid_ids = [event['_id'] for event in events if not verify_local_integrity(event)]
    return {'lot_id': lot_id, 'local_consistency': not invalid_ids,
            'checked_events': len(events), 'invalid_events_count': len(invalid_ids),
            'truncated': len(events) == 500,
            'note': 'Contrôle local SHA-256 : il ne constitue pas une certification indépendante.'}


@router.get('/lots/{lot_id}/qr')
def qr_lot(lot_id: str, request: Request, user=Depends(authenticated_user)):
    lot = ensure_lot(database(request), lot_id, user)
    base = os.getenv('FRONTEND_PUBLIC_URL', 'http://127.0.0.1:5173').rstrip('/')
    target = f'{base}/?lot={lot_id}'
    im = qrcode.make(target)
    output = io.BytesIO()
    im.save(output, format='PNG')
    return {'lot_code': lot['code'], 'target': target,
            'image_data_url': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')}


@router.post('/lots/{lot_id}/germination')
def germination(lot_id: str, data: GerminationIn, request: Request,
                key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
                actor=Depends(require_role('production'))):
    db = database(request)
    def handler(lot, session):
        guarantee(lot.get('lotType', 'SEMIS') == 'SEMIS' and 'plantsInStock' not in lot, 'Germination déjà enregistrée ou lot non issu du semis.')
        guarantee(data.quantity <= lot['quantitySown'], 'Quantité germée supérieure à la quantité semée.')
        guarantee(data.observed_on.isoformat() >= lot['sownOn'], 'Date antérieure au semis.')
        guarantee(lot['sownOn'] <= data.started_on.isoformat() <= data.ended_on.isoformat() <= data.observed_on.isoformat(),
                  'Dates de germination incohérentes avec le semis et l’observation.')
        guarantee(data.observed_on <= date.today(), 'La germination réelle ne peut pas être datée dans le futur.')
        max_hours = ((data.ended_on - data.started_on).days + 1) * 24
        guarantee(data.duration_hours <= max_hours,
                  'Durée de germination incohérente avec les dates indiquées.')
        return ({'plantsInStock': data.quantity, 'plantsLost': 0, 'plantsReserved': 0,
                 'plantsDelivered': 0, 'plantsReturned': 0, 'qualityApproved': 0,
                 'qualityStatus': 'NON_CONTROLE', 'locations': {data.location: data.quantity},
                 'reservedLocations': {}, 'status': 'EN_PRODUCTION'},
                {'quantite_germee': data.quantity, 'quantite_semee': lot['quantitySown'],
                 'emplacement': data.location, 'temperature': data.temperature,
                 'humidite': data.humidity, 'debut': data.started_on.isoformat(),
                 'fin': data.ended_on.isoformat(), 'duree_heures': data.duration_hours,
                 'date': data.observed_on.isoformat(), 'notes': data.notes}, None)
    return execute(db, lot_id, actor, 'production', key, 'GERMINATION', handler)


@router.post('/lots/{lot_id}/transfer')
def transfer(lot_id: str, data: TransferIn, request: Request,
             key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
             actor=Depends(require_role('production'))):
    db = database(request)
    def handler(lot, session):
        guarantee('plantsInStock' in lot, 'Enregistrez la germination auparavant.')
        guarantee(data.origin != data.destination, 'L’emplacement de départ et d’arrivée doivent être différents.')
        guarantee(location_available(lot, data.origin) >= data.quantity, 'Quantité disponible insuffisante à cet emplacement.')
        guarantee(lot.get('plantsReserved', 0) == 0,
                  'Transfert bloqué : commande déjà préparée. Terminez ou annulez la préparation.')
        locations = dict(lot['locations'])
        locations[data.origin] -= data.quantity
        locations[data.destination] = locations.get(data.destination, 0) + data.quantity
        return ({'locations': locations, 'status': 'EN_PRODUCTION',
                 'qualityStatus':'A_RECONTROLER','qualityApproved':0},
                {'quantite': data.quantity, 'origine': data.origin, 'destination': data.destination, 'notes': data.notes}, None)
    return execute(db, lot_id, actor, 'production', key, 'TRANSFERT', handler)


@router.post('/lots/{lot_id}/loss')
def loss(lot_id: str, data: LossIn, request: Request,
         key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
         actor=Depends(require_role('production'))):
    db = database(request)
    def handler(lot, session):
        guarantee(location_available(lot, data.location) >= data.quantity, 'Pertes supérieures aux plants non réservés à cet emplacement.')
        guarantee(lot.get('plantsReserved', 0) == 0, 'Annulez ou terminez les préparations avant de déclarer des pertes.')
        locations = dict(lot.get('locations', {}))
        locations[data.location] -= data.quantity
        return ({'locations': locations, 'plantsInStock': lot['plantsInStock']-data.quantity,
                 'plantsLost': lot.get('plantsLost', 0)+data.quantity,
                 'qualityStatus': 'A_RECONTROLER', 'qualityApproved': 0, 'status': 'EN_PRODUCTION'},
                {'quantite': data.quantity, 'emplacement': data.location, 'motif': data.reason}, None)
    return execute(db, lot_id, actor, 'production', key, 'PERTES', handler)


@router.post('/lots/{lot_id}/treatment')
def treatment(lot_id: str, data: TreatmentIn, request: Request,
              key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
              actor=Depends(require_role('production'))):
    db = database(request)
    def handler(lot, session):
        guarantee('plantsInStock' in lot, 'Enregistrez la germination auparavant.')
        guarantee(data.location in lot.get('locations', {}), 'Emplacement inconnu pour ce lot.')
        guarantee(lot.get('plantsReserved', 0) == 0, 'Préparations en cours : traitement bloqué en pilote.')
        guarantee(data.performed_on <= date.today(), 'Intervention dans le futur non autorisée.')
        guarantee(data.performed_on.isoformat() >= (lot.get('sownOn') or '1900-01-01'),
                  'Intervention datée avant le semis du lot.')
        guarantee(data.intervention_type != 'TRAITEMENT' or bool(data.product.strip()),
                  'Indiquez le produit utilisé pour un traitement.')
        return ({'qualityStatus': 'A_RECONTROLER', 'qualityApproved': 0},
                {'intervention': data.name, 'type': data.intervention_type,
                 'produit': data.product, 'dose': data.dose, 'date': data.performed_on.isoformat(),
                 'emplacement': data.location, 'notes': data.notes}, None)
    return execute(db, lot_id, actor, 'production', key, 'INTERVENTION', handler)


@router.post('/lots/{lot_id}/graft')
def graft(lot_id: str, data: GraftIn, request: Request,
          key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
          actor=Depends(require_role('production'))):
    db = database(request)
    guarantee(data.rootstock_lot_id != lot_id, 'Le porte-greffe doit provenir d’un lot distinct.')
    guarantee(data.quantity_success <= data.quantity_used, 'Réussites supérieures aux plants greffés.')
    def handler(lot, session):
        root = ensure_lot(db, data.rootstock_lot_id, actor, session)
        guarantee(root['siteCode'] == lot['siteCode'], 'Les deux lots doivent appartenir au même site pour ce pilote.')
        guarantee('plantsInStock' in root and 'plantsInStock' in lot, 'Germination/stock des deux parents requis.')
        guarantee(data.grafted_on <= date.today(), 'Date de greffage future non autorisée.')
        guarantee(data.grafted_on.isoformat() >= max(lot.get('sownOn') or '1900-01-01', root.get('sownOn') or '1900-01-01'),
                  'Date de greffage antérieure au semis d’un parent.')
        guarantee(lot.get('plantsReserved', 0) == root.get('plantsReserved', 0) == 0,
                  'Des préparations sont en cours sur un des lots.')
        guarantee(location_available(lot, data.scion_location) >= data.quantity_used,
                  'Greffons insuffisants à cet emplacement.')
        guarantee(location_available(root, data.rootstock_location) >= data.quantity_used,
                  'Porte-greffes insuffisants à cet emplacement.')
        root_locations = dict(root['locations'])
        root_locations[data.rootstock_location] -= data.quantity_used
        commit_lot(db, root, {'locations': root_locations,
                              'plantsInStock': root['plantsInStock']-data.quantity_used,
                              'plantsUsedForGrafting': root.get('plantsUsedForGrafting', 0)+data.quantity_used,
                              'qualityStatus': 'A_RECONTROLER', 'qualityApproved': 0}, session)
        locations = dict(lot['locations']); locations[data.scion_location] -= data.quantity_used
        child_id = str(uuid4())
        code = f"RP-G-{now().year}-{uuid4().hex[:8].upper()}"
        child = {'_id': child_id, 'code': code, 'siteCode': lot['siteCode'],
                 'seedLotId': lot.get('seedLotId'), 'species': lot.get('species'),
                 'article': lot.get('article'), 'variety': lot.get('variety'),
                 'campaign': lot.get('campaign') or campaign_for_date(lot.get('sownOn')),
                 'lotType': 'GREFFE', 'parentLotIds': [lot_id, root['_id']],
                 'quantitySown': None, 'sownOn': lot.get('sownOn'),
                 'plantsInStock': data.quantity_success, 'plantsLost': data.quantity_used-data.quantity_success,
                 'plantsReserved': 0, 'plantsDelivered': 0, 'plantsReturned': 0,
                 'plantsUsedForGrafting': 0, 'qualityApproved': 0, 'qualityStatus': 'NON_CONTROLE',
                 'locations': {data.scion_location: data.quantity_success}, 'reservedLocations': {},
                 'status': 'EN_PRODUCTION', 'revision': 0, 'createdAt': now()}
        db.production_lots.insert_one(child, session=session)
        register_operational(db, child, session)
        return ({'locations': locations,
                 'plantsInStock': lot['plantsInStock']-data.quantity_used,
                 'plantsUsedForGrafting': lot.get('plantsUsedForGrafting', 0)+data.quantity_used,
                 'qualityStatus': 'A_RECONTROLER', 'qualityApproved': 0},
                {'parent_lot_ids': [lot_id, root['_id']], 'lot_fils': code, 'lot_fils_id': child_id,
                 'quantite_utilisee': data.quantity_used, 'quantite_reussie': data.quantity_success,
                 'pertes_greffage': data.quantity_used-data.quantity_success,
                 'date': data.grafted_on.isoformat(), 'variete_greffon': lot.get('variety'),
                 'variete_porte_greffe': root.get('variety'), 'lot_porte_greffe': root['code'],
                 'emplacement': data.scion_location, 'notes': data.notes}, {'child_lot': serial_lot(child)})
    return execute(db, lot_id, actor, 'production', key, 'GREFFAGE', handler)


@router.post('/lots/{lot_id}/quality')
def quality(lot_id: str, data: QualityIn, request: Request,
            key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
            actor=Depends(require_role('qualite'))):
    db = database(request)
    def handler(lot, session):
        guarantee('plantsInStock' in lot, 'Germination ou production non enregistrée.')
        guarantee(data.inspected_on <= date.today(), 'Date du contrôle qualité future non autorisée.')
        guarantee(data.inspected_on.isoformat() >= (lot.get('sownOn') or '1900-01-01'),
                  'Contrôle qualité daté avant le semis.')
        guarantee(not data.approved or (data.sanitary_status == 'SAIN' and data.homogeneity == 'HOMOGENE'),
                  'Impossible de libérer un lot avec état sanitaire ou homogénéité défavorable.')
        guarantee(lot.get('plantsReserved', 0) == 0, 'Préparations en cours : contrôle qualité non modifiable.')
        guarantee(data.inspected_quantity <= lot['plantsInStock'], 'Nombre inspecté supérieur au stock.')
        guarantee(data.approved_quantity <= data.inspected_quantity, 'Quantité conforme supérieure à la quantité inspectée.')
        guarantee((data.approved and data.approved_quantity > 0) or (not data.approved and data.approved_quantity == 0),
                  'Décision et quantité conforme incompatibles.')
        status = 'CONFORME' if data.approved else 'BLOQUE'
        return ({'qualityStatus': status, 'qualityApproved': data.approved_quantity, 'status': status},
                {'conforme': data.approved, 'quantite_inspectee': data.inspected_quantity,
                 'quantite_commercialisable': data.approved_quantity,
                 'etat_sanitaire': data.sanitary_status, 'homogeneite': data.homogeneity,
                 'date_controle': data.inspected_on.isoformat(), 'observations': data.notes}, None)
    return execute(db, lot_id, actor, 'qualite', key, 'CONTROLE_QUALITE', handler)


@router.post('/lots/{lot_id}/preparation')
def preparation(lot_id: str, data: PreparationIn, request: Request,
                key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
                actor=Depends(require_role('logistique'))):
    db = database(request)
    def handler(lot, session):
        guarantee(lot.get('qualityStatus') == 'CONFORME', 'Livraison bloquée : contrôle qualité non conforme.')
        if db.preparations.find_one({'lotId': lot_id, 'client': data.client.strip(),
                                     'orderReference': data.order_reference.strip()}, session=session):
            raise HTTPException(409, 'Cette commande est déjà préparée pour ce lot et client.')
        guarantee(location_available(lot, data.location) >= data.quantity, 'Stock disponible insuffisant sur cet emplacement.')
        guarantee(lot.get('qualityApproved', 0) - lot.get('plantsReserved', 0) >= data.quantity,
                  'Quantité commercialisable autorisée insuffisante.')
        prep_id = str(uuid4())
        prep = {'_id': prep_id, 'lotId': lot_id, 'siteCode': lot['siteCode'], 'client': data.client,
                'orderReference': data.order_reference, 'location': data.location,
                'quantityReserved': data.quantity, 'quantityDelivered': 0, 'quantityReturned': 0,
                'trays': data.trays, 'pallets': data.pallets, 'createdAt': now()}
        db.preparations.insert_one(prep, session=session)
        reserved_locs = dict(lot.get('reservedLocations', {}))
        reserved_locs[data.location] = reserved_locs.get(data.location, 0)+data.quantity
        return ({'plantsReserved': lot.get('plantsReserved', 0)+data.quantity,
                 'reservedLocations': reserved_locs},
                {'preparation_id': prep_id, 'client': data.client, 'commande': data.order_reference,
                 'quantite': data.quantity, 'emplacement': data.location, 'plateaux': data.trays,
                 'palettes': data.pallets}, {'preparation_id': prep_id})
    return execute(db, lot_id, actor, 'logistique', key, 'PREPARATION', handler)


@router.post('/lots/{lot_id}/delivery')
def delivery(lot_id: str, data: DeliveryIn, request: Request,
             key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
             actor=Depends(require_role('logistique'))):
    db = database(request)
    def handler(lot, session):
        p = db.preparations.find_one({'_id': data.preparation_id, 'lotId': lot_id}, session=session)
        guarantee(p is not None, 'Préparation de commande introuvable.')
        guarantee(lot.get('qualityStatus') == 'CONFORME', 'Livraison bloquée : lot non conforme.')
        guarantee(p['quantityReserved'] - p['quantityDelivered'] >= data.quantity,
                  'Quantité supérieure au reliquat de la préparation.')
        guarantee(lot.get('reservedLocations', {}).get(p['location'], 0) >= data.quantity,
                  'Stock réservé insuffisant sur cet emplacement.')
        guarantee(lot.get('locations', {}).get(p['location'], 0) >= data.quantity,
                  'Stock physique insuffisant.')
        guarantee(data.delivered_on.isoformat() >= (lot.get('sownOn') or '1900-01-01'), 'Date de livraison antérieure au semis.')
        guarantee(data.delivered_on <= date.today(), 'La livraison effectuée ne peut pas être datée dans le futur.')
        guarantee(data.receipt_confirmed, 'Réception client non confirmée : ne marquez pas cette livraison comme reçue.')
        db.preparations.update_one({'_id': p['_id']}, {'$inc': {'quantityDelivered': data.quantity}}, session=session)
        delivery_id = str(uuid4())
        db.deliveries.insert_one({'_id': delivery_id, 'siteCode': lot['siteCode'], 'lotId': lot_id,
            'preparationId': p['_id'], 'client': p['client'], 'quantity': data.quantity,
            'deliveryNote': data.delivery_note, 'transporter': data.transporter,
            'vehicle': data.vehicle, 'receivedBy': data.received_by,
            'receiptConfirmed': data.receipt_confirmed, 'date': data.delivered_on.isoformat(),
            'createdAt': now()}, session=session)
        locs = dict(lot['locations']); locs[p['location']] -= data.quantity
        reserved_locs = dict(lot['reservedLocations']); reserved_locs[p['location']] -= data.quantity
        return ({'plantsInStock': lot['plantsInStock']-data.quantity,
                 'plantsReserved': lot['plantsReserved']-data.quantity,
                 'plantsDelivered': lot.get('plantsDelivered', 0)+data.quantity,
                 'qualityApproved': lot.get('qualityApproved', 0)-data.quantity,
                 'locations': locs, 'reservedLocations': reserved_locs},
                {'livraison_id': delivery_id, 'preparation_id': p['_id'],
                 'bon_livraison': data.delivery_note, 'client': p['client'],
                 'quantite_livree': data.quantity, 'transporteur': data.transporter,
                 'vehicule': data.vehicle, 'receptionnaire': data.received_by,
                 'reception_confirmee': data.receipt_confirmed, 'date': data.delivered_on.isoformat()}, {'delivery_id': delivery_id})
    return execute(db, lot_id, actor, 'logistique', key, 'LIVRAISON', handler)


@router.post('/lots/{lot_id}/return')
def return_plants(lot_id: str, data: ReturnIn, request: Request,
                 key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
                 actor=Depends(require_role('logistique'))):
    db = database(request)
    def handler(lot, session):
        p = db.preparations.find_one({'_id': data.preparation_id, 'lotId': lot_id}, session=session)
        guarantee(p is not None, 'Préparation de commande introuvable.')
        guarantee(p['quantityDelivered'] - p.get('quantityReturned', 0) >= data.quantity,
                  'Le retour excède la quantité nette déjà livrée.')
        prior_deliveries = list(db.deliveries.find({'preparationId': p['_id'],
                                                   'date': {'$lte': data.returned_on.isoformat()}}, session=session))
        guarantee(sum(d['quantity'] for d in prior_deliveries)-p.get('quantityReturned',0) >= data.quantity,
                  'Retour impossible avant la date ou la quantité réelle des livraisons.')
        guarantee(data.returned_on.isoformat() >= (lot.get('sownOn') or '1900-01-01'), 'Date de retour invalide.')
        # Returns become a separate quarantined child: NEVER automatically put returned plants into salable stock.
        child_id = str(uuid4()); code = f'RP-RET-{now().year}-{uuid4().hex[:8].upper()}'
        child = {'_id': child_id, 'code': code, 'siteCode': lot['siteCode'], 'variety': lot.get('variety'),
                 'seedLotId': lot.get('seedLotId'), 'lotType': 'RETOUR', 'parentLotIds': [lot_id],
                 'quantitySown': None, 'sownOn': lot.get('sownOn'),
                 'plantsInStock': data.quantity, 'plantsLost': 0, 'plantsReserved': 0,
                 'plantsDelivered': 0, 'plantsReturned': 0, 'qualityApproved': 0,
                 'qualityStatus': 'BLOQUE', 'locations': {'QUARANTAINE': data.quantity},
                 'reservedLocations': {}, 'status': 'QUARANTAINE', 'revision': 0, 'createdAt': now()}
        db.production_lots.insert_one(child, session=session)
        register_operational(db, child, session)
        db.preparations.update_one({'_id': p['_id']}, {'$inc': {'quantityReturned': data.quantity}}, session=session)
        return ({'plantsReturned': lot.get('plantsReturned', 0)+data.quantity},
                {'preparation_id': p['_id'], 'quantite_retour': data.quantity, 'motif': data.reason,
                 'date': data.returned_on.isoformat(), 'lot_fils': code,
                 'lot_fils_id': child_id, 'parent_lot_ids': [lot_id]}, {'child_lot': serial_lot(child)})
    return execute(db, lot_id, actor, 'logistique', key, 'RETOUR', handler)


@router.post('/lots/{lot_id}/correction')
def correction(lot_id: str, data: CorrectionIn, request: Request,
               key: Annotated[str | None, Header(alias='Idempotency-Key')] = None,
               actor=Depends(require_role('admin'))):
    db = database(request)
    def handler(lot, session):
        old = db.trace_events.find_one({'_id': data.original_event_id, 'subjectId': lot_id}, session=session)
        guarantee(old is not None, 'Événement d’origine introuvable.')
        return ({}, {'evenement_reference': old['_id'], 'note': data.note,
                      'avertissement': 'Note seulement : aucun stock modifié.'}, None)
    return execute(db, lot_id, actor, 'admin', key, 'NOTE_CORRECTION', handler)
