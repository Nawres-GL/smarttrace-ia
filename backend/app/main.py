"""Royal Plants SmartTrace API — authenticated, pilot-only workflow.

MongoDB Atlas is the operational source of truth. Original Excel files are read-only.
Validated operations are stored with a local, hashed audit history.
Not production-hardened: do not expose customer data on a public deployment yet.
"""
import os
from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.auth import authenticated_user, require_role, require_site, router as auth_router
from app.ledger import event_public, insert_event, make_event, now
from app.campaigns import campaign_for_date

load_dotenv()
if os.getenv('APP_ENV', 'development') != 'development':
    raise RuntimeError('Pilot safeguards: public deployment needs a security and operations review.')

URI = os.getenv('MONGODB_URI', '')
DB_NAME = os.getenv('MONGODB_DB', 'royal_plants_smarttrace_dev')
client = MongoClient(URI, serverSelectionTimeoutMS=10000, retryWrites=True) if URI else None
db = client[DB_NAME] if client is not None else None


def as_seed(row):
    return {'id': row['_id'], 'site_code': row['siteCode'], 'supplier': row['supplier'],
            'supplier_lot_number': row['supplierLotNumber'], 'species': row.get('species'), 'article': row.get('article', row.get('variety')), 'variety': row['variety'],
            'quantity_received': row['quantityReceived'], 'quantity_allocated': row['quantityAllocated'],
            'received_on': row['receivedOn']}


def as_lot(row):
    return {'id': row['_id'], 'code': row['code'], 'site_code': row['siteCode'],
            'seed_lot_id': row.get('seedLotId'), 'species': row.get('species'), 'article': row.get('article', row.get('variety')), 'variety': row.get('variety'),
            'campaign': row.get('campaign') or campaign_for_date(row.get('sownOn')),
            'quantity_sown': row.get('quantitySown'), 'sown_on': row.get('sownOn'),
            'status': row.get('status'), 'revision': row.get('revision', 0)}


@asynccontextmanager
async def lifespan(app):
    if client is None:
        yield
        return
    client.admin.command('ping')
    db.users.create_index('email', unique=True)
    db.access_audit.create_index([('targetId', ASCENDING), ('at', DESCENDING)])
    db.sites.create_index('code', unique=True)
    db.seed_lots.create_index([('siteCode', ASCENDING), ('supplier', ASCENDING),
                               ('supplierLotNumber', ASCENDING), ('variety', ASCENDING)], unique=True)
    db.production_lots.create_index('code', unique=True)
    db.lot_registry.create_index([('kind', ASCENDING), ('code', ASCENDING)])
    db.production_lots.create_index('seedLotId')
    db.trace_events.create_index([('subjectType', ASCENDING), ('subjectId', ASCENDING), ('occurredAtDt', ASCENDING)])
    db.trace_events.create_index('idempotencyKey', unique=True, sparse=True)
    db.preparations.create_index([('lotId', ASCENDING), ('createdAt', DESCENDING)])
    db.deliveries.create_index([('lotId', ASCENDING), ('createdAt', DESCENDING)])
    db.investigation_cases.create_index([('siteCode', ASCENDING), ('updatedAt', DESCENDING)])
    db.investigation_cases.create_index([('lotId', ASCENDING), ('updatedAt', DESCENDING)])
    db.sites.update_one({'code': 'S01'}, {'$setOnInsert': {'code': 'S01', 'name': 'Site pilote'}}, upsert=True)
    yield
    client.close()


app = FastAPI(title='Royal Plants SmartTrace', version='1.0.0', lifespan=lifespan)
app.state.db = db

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not return exc.errors()[...]['input']: passwords and tokens may be present.
    errors = [{'field': '.'.join(str(part) for part in error['loc'] if part != 'body'),
               'message': error['msg']} for error in exc.errors()]
    return JSONResponse(status_code=422, content={'detail': 'Données invalides. Vérifiez les champs indiqués.', 'errors': errors})

@app.exception_handler(PyMongoError)
async def database_error(request: Request, exc: PyMongoError):
    # No connection strings, server internals or business records returned.
    return JSONResponse(status_code=503, content={'detail': 'Base de données indisponible ou opération interrompue. Réessayez.'})

app.add_middleware(CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',') if x.strip()],
    allow_credentials=False, allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type', 'Authorization', 'Idempotency-Key'])


class SeedLotIn(BaseModel):
    site_code: str = Field(default='S01', min_length=1, max_length=20)
    supplier: str = Field(min_length=1, max_length=120)
    supplier_lot_number: str = Field(min_length=1, max_length=80)
    species: str = Field(min_length=2, max_length=120)
    article: str | None = Field(default=None, max_length=120)
    variety: str = Field(min_length=1, max_length=120)
    quantity_received: int = Field(gt=0)
    received_on: date


class ProductionLotIn(BaseModel):
    site_code: str = Field(default='S01', min_length=1, max_length=20)
    seed_lot_id: str = Field(min_length=1)
    quantity_sown: int = Field(gt=0)
    sown_on: date
    tray_type: str = Field(min_length=2, max_length=80)
    tray_count: int = Field(gt=0)
    tray_capacity: int = Field(gt=0, le=10000)
    substrate: str = Field(min_length=2, max_length=120)


@app.get('/api/health')
def health():
    if client is None:
        return {'status': 'ok', 'mongo_connected': False, 'message': 'Mode local sans Atlas'}
    try:
        client.admin.command('ping')
    except PyMongoError:
        raise HTTPException(503, 'MongoDB Atlas indisponible.')
    return {'status': 'ok', 'mongo_connected': True, 'message': 'API SmartTrace opérationnelle'}


@app.get('/api/sites')
def sites(user=Depends(authenticated_user)):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    where = {} if user['role'] == 'admin' else {'code': {'$in': user.get('siteCodes', [])}}
    return [{'code': x['code'], 'name': x['name']} for x in db.sites.find(where, {'_id': 0})]


class SiteIn(BaseModel):
    code: str = Field(pattern=r'^[A-Za-z0-9_-]{2,20}$')
    name: str = Field(min_length=2, max_length=120)


@app.post('/api/sites', status_code=201)
def create_site(data: SiteIn, user=Depends(require_role('admin'))):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    try:
        db.sites.insert_one({'code': data.code.upper(), 'name': data.name.strip()})
    except DuplicateKeyError:
        raise HTTPException(409, 'Ce code site existe déjà.')
    return {'code': data.code.upper(), 'name': data.name.strip()}


@app.get('/api/seed-lots')
def seed_lots(user=Depends(authenticated_user)):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    where = {} if user['role'] == 'admin' else {'siteCode': {'$in': user.get('siteCodes', [])}}
    return [as_seed(x) for x in db.seed_lots.find(where).sort('receivedOn', DESCENDING).limit(250)]


@app.post('/api/seed-lots', status_code=201)
def create_seed_lot(data: SeedLotIn, user=Depends(require_role('production'))):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    require_site(user, data.site_code)
    if not db.sites.find_one({'code': data.site_code}):
        raise HTTPException(422, 'Site de production inconnu.')
    row = {'_id': str(uuid4()), 'siteCode': data.site_code, 'supplier': data.supplier.strip(),
           'supplierLotNumber': data.supplier_lot_number.strip(), 'species': data.species.strip().title(),
           'article': (data.article or data.variety).strip(), 'variety': data.variety.strip(),
           'quantityReceived': data.quantity_received, 'quantityAllocated': 0,
           'receivedOn': data.received_on.isoformat(), 'createdAt': now()}
    event = make_event('SEED_LOT', row['_id'], data.site_code, 'RECEPTION_SEMENCES',
        {'fournisseur': row['supplier'], 'reference': row['supplierLotNumber'],
         'espece': row['species'], 'article': row['article'], 'variete': row['variety'], 'quantite': row['quantityReceived'], 'date': row['receivedOn']}, user['_id'])
    try:
        with client.start_session() as session:
            session.with_transaction(lambda s: (db.seed_lots.insert_one(row, session=s), insert_event(db, event, s)))
    except DuplicateKeyError:
        raise HTTPException(409, 'Ce lot de semences fournisseur existe déjà.')
    return as_seed(row)


@app.get('/api/lots')
def lots(user=Depends(authenticated_user)):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    where = {} if user['role'] == 'admin' else {'siteCode': {'$in': user.get('siteCodes', [])}}
    return [as_lot(x) for x in db.production_lots.find(where).sort('createdAt', DESCENDING).limit(200)]


@app.post('/api/lots', status_code=201)
def create_lot(data: ProductionLotIn, user=Depends(require_role('production')),
               idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    require_site(user, data.site_code)
    if not idempotency_key or len(idempotency_key) < 12:
        raise HTTPException(400, 'Clé de requête manquante.')
    existing = db.trace_events.find_one({'idempotencyKey': idempotency_key})
    if existing:
        if existing.get('actorId') != user['_id']:
            raise HTTPException(403, 'Clé de requête appartenant à un autre opérateur.')
        if existing['eventType'] != 'SEMIS':
            raise HTTPException(409, 'Clé déjà utilisée pour une autre opération.')
        old = db.production_lots.find_one({'_id': existing['subjectId']})
        if old:
            require_site(user, old['siteCode'])
            return as_lot(old)
    seed = db.seed_lots.find_one({'_id': data.seed_lot_id})
    if seed is None:
        raise HTTPException(404, 'Lot de semences introuvable.')
    if seed['siteCode'] != data.site_code:
        raise HTTPException(422, 'Site incompatible avec ce lot de semences.')
    if data.sown_on.isoformat() < seed['receivedOn']:
        raise HTTPException(422, 'La date de semis ne peut pas précéder la réception.')
    if data.quantity_sown > data.tray_count * data.tray_capacity:
        raise HTTPException(422, 'La quantité semée dépasse la capacité des plateaux déclarés.')
    if data.sown_on > date.today():
        raise HTTPException(422, 'Le semis réel ne peut pas être daté dans le futur.')
    row = {'_id': str(uuid4()), 'code': f'RP-{data.site_code}-{data.sown_on.year}-{uuid4().hex[:8].upper()}',
           'siteCode': data.site_code, 'seedLotId': seed['_id'], 'species': seed.get('species'),
           'article': seed.get('article') or seed['variety'], 'variety': seed['variety'], 'campaign': campaign_for_date(data.sown_on),
           'lotType': 'SEMIS', 'parentLotIds': [], 'quantitySown': data.quantity_sown, 'trayType': data.tray_type.strip(),
           'trayCount': data.tray_count, 'trayCapacity': data.tray_capacity, 'substrate': data.substrate.strip(),
           'sownOn': data.sown_on.isoformat(), 'status': 'SEMIS_ENREGISTRE', 'revision': 0,
           'plantsLost': 0, 'plantsReserved': 0, 'plantsDelivered': 0, 'plantsReturned': 0,
           'qualityStatus': 'NON_CONTROLE', 'qualityApproved': 0, 'createdAt': now()}
    event = make_event('PRODUCTION_LOT', row['_id'], data.site_code, 'SEMIS',
        {'code_lot': row['code'], 'lot_semences': seed['_id'], 'espece': seed.get('species'), 'variete': seed['variety'],
         'quantite_semee': data.quantity_sown, 'date': row['sownOn'],
         'type_plateau': row['trayType'], 'nombre_plateaux': row['trayCount'],
         'capacite_plateau': row['trayCapacity'], 'substrat': row['substrate'],
         'operateur_id': user['_id']}, user['_id'])
    event['idempotencyKey'] = idempotency_key

    def tx(session):
        previous = db.trace_events.find_one({'idempotencyKey': idempotency_key}, session=session)
        if previous:
            if previous.get('actorId') != user['_id']:
                raise HTTPException(403, 'Clé de requête appartenant à un autre opérateur.')
            old = db.production_lots.find_one({'_id': previous['subjectId']}, session=session)
            if old and previous['eventType'] == 'SEMIS':
                return as_lot(old)
            raise HTTPException(409, 'Clé de requête réutilisée.')
        updated = db.seed_lots.find_one_and_update(
            {'_id': seed['_id'], 'siteCode': data.site_code,
             '$expr': {'$lte': [{'$add': ['$quantityAllocated', data.quantity_sown]}, '$quantityReceived']}},
            {'$inc': {'quantityAllocated': data.quantity_sown}},
            return_document=ReturnDocument.AFTER, session=session)
        if updated is None:
            raise HTTPException(422, 'Quantité de semences disponible insuffisante.')
        db.production_lots.insert_one(row, session=session)
        from app.unified_registry import operational_entry
        db.lot_registry.update_one({'_id':'operational:'+row['_id']},
             {'$set':operational_entry(row)},upsert=True,session=session)
        insert_event(db, event, session)
        return as_lot(row)

    try:
        with client.start_session() as session:
            return session.with_transaction(tx)
    except DuplicateKeyError:
        saved = db.trace_events.find_one({'idempotencyKey': idempotency_key})
        if saved and saved['eventType'] == 'SEMIS' and saved.get('actorId') == user['_id']:
            found = db.production_lots.find_one({'_id': saved['subjectId']})
            if found:
                require_site(user, found['siteCode'])
                return as_lot(found)
        raise HTTPException(409, 'Semis déjà enregistré.')


@app.get('/api/lots/{lot_id}/events')
def lot_events(lot_id: str, user=Depends(authenticated_user)):
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis.')
    lot = db.production_lots.find_one({'_id': lot_id})
    if lot is None:
        raise HTTPException(404, 'Lot de production introuvable.')
    require_site(user, lot['siteCode'])
    filt = {'$or': [
        {'subjectType': 'SEED_LOT', 'subjectId': lot.get('seedLotId')},
        {'subjectType': 'PRODUCTION_LOT', 'subjectId': lot_id},
        {'details.parent_lot_ids': lot_id},
        {'details.lot_fils_id': lot_id},
    ]}
    return {'lot': as_lot(lot), 'events': [event_public(x) for x in db.trace_events.find(filt).sort('occurredAtDt', ASCENDING)]}


from app.operations import router as operational_router
from app.history import router as historical_router
from nlp.api import router as nlp_router
app.include_router(auth_router)
app.include_router(operational_router)
from app.investigations import router as investigations_router
app.include_router(investigations_router)
from app.investigation_cases import router as investigation_cases_router
app.include_router(investigation_cases_router)
# Historical financial/customer data are never public. Site mapping for Excel is unknown;
# pilot access is admin-only until source-site relationships can be validated.
app.include_router(historical_router, dependencies=[Depends(require_role('admin'))])
from app.historical_imports import router as historical_import_router
app.include_router(historical_import_router)
from app.unified_registry import router as unified_registry_router
app.include_router(unified_registry_router)
from app.insights import router as insights_router
app.include_router(insights_router)
from app.data_quality import router as data_quality_router
app.include_router(data_quality_router)
from rag.api import router as rag_router
app.include_router(nlp_router)
app.include_router(rag_router)
