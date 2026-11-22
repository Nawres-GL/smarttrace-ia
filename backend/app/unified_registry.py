"""Unified lot index and authenticated QR lookups.

Historical lot associations are *candidate matches* based on five-digit codes.
No Excel row becomes a certified operation or live inventory.
"""
from __future__ import annotations
import base64
import io
import os
import re
from datetime import datetime, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.auth import require_role, authenticated_user, database, require_site
from app.history import load_historical, summarize
from etl.pipeline import lot_five_digits

router = APIRouter(prefix='/api/registry', tags=['Registre unifié et QR'])
LOT_RE = re.compile(r'^\d{5}$')


def registry_historical_id(code):
    if not LOT_RE.fullmatch(str(code)):
        raise ValueError('Le code historique doit contenir exactement 5 chiffres.')
    return 'historical:' + str(code)


def build_historical_entry(code, production, deliveries, grafts):
    """Safe metadata only, with source counts and candidate-match warning."""
    summary = summarize(code, production, deliveries, grafts)
    return {'_id': registry_historical_id(code), 'kind': 'historical', 'code': code,
            'species': summary['species_label'], 'article': summary['article_label'],
            'varieties': summary['varieties'], 'campaign': summary['campaign'],
            'counts': {'production': len(production), 'livraison': len(deliveries), 'greffage': len(grafts)},
            'linkStatus': summary['status'],
            'linkConfidence': 'CANDIDATE_FIVE_DIGIT',
            'source': 'ARCHIVES_EXCEL_ATLAS'}


def sync_historical_registry(db, codes=None):
    """Rebuild only requested historical codes from the source collections.

    Called on bootstrap and incremental updates; no automatic merge with live stock.
    Existing historical registry documents stay stable by deterministic ID.
    """
    if codes is None:
        codes = (set(db.historical_production_records.distinct('lot_code')) |
                 set(db.historical_delivery_lines.distinct('lot_code')) |
                 set(db.historical_grafting_records.distinct('lot_code')))
    codes = {str(c) for c in codes if c and LOT_RE.fullmatch(str(c))}
    changed = 0
    for code in sorted(codes):
        p = list(db.historical_production_records.find({'lot_code': code}))
        d = list(db.historical_delivery_lines.find({'lot_code': code}))
        g = list(db.historical_grafting_records.find({'lot_code': code}))
        if not (p or d or g):
            continue
        entry = build_historical_entry(code, p, d, g)
        db.lot_registry.update_one({'_id':entry['_id']},
            {'$set': {**entry, 'updatedAt':datetime.now(timezone.utc)}},upsert=True)
        changed += 1
    return changed


def operational_entry(lot):
    return {'_id':'operational:'+lot['_id'], 'kind':'operational',
            'code':lot['code'], 'operationalLotId':lot['_id'],
            'siteCode':lot['siteCode'], 'species':lot.get('species') or '',
            'article':lot.get('article') or lot.get('variety') or '',
            'varieties':[lot['variety']] if lot.get('variety') else [],
            'campaign':lot.get('campaign'), 'source':'OPERATIONS_MONGODB'}


def register_operational(db, lot, session=None):
    """Atomically materialize each new live lot within the business transaction."""
    entry=operational_entry(lot)
    db.lot_registry.update_one({'_id':entry['_id']}, {'$set':entry},upsert=True,session=session)


def sync_operational_registry(db):
    count=0
    for lot in db.production_lots.find({}):
        entry=operational_entry(lot)
        db.lot_registry.update_one({'_id':entry['_id']}, {'$set':entry},upsert=True)
        count+=1
    return count


def qr_payload(kind, code, frontend_url=None):
    # URLs carry ONLY a public lot reference, never a token or customer details.
    base=(frontend_url or os.getenv('FRONTEND_PUBLIC_URL','http://127.0.0.1:5173')).rstrip('/')
    from urllib.parse import quote
    if kind=='historical':
        registry_historical_id(code)
        target=base+'/?trace='+quote('historical:'+code,safe='')
    elif kind=='operational':
        target=base+'/?lot='+quote(str(code),safe='')
    else:
        raise ValueError('Type de lot non pris en charge.')
    image=qrcode.make(target)
    buff=io.BytesIO();image.save(buff,format='PNG')
    return {'target':target,'image_data_url':'data:image/png;base64,'+base64.b64encode(buff.getvalue()).decode('ascii')}


@router.get('/historical/{code}/qr')
def historical_qr(code:str, request:Request, user=Depends(require_role('admin'))):
    if not LOT_RE.fullmatch(code):
        raise HTTPException(422, 'Saisissez un code historique à cinq chiffres.')
    db=database(request)
    if not db.lot_registry.find_one({'_id':'historical:'+code}):
        # Support existing Excel mode during migration, but still require a real lot.
        from app.history import catalogue
        if not any(row['lot_code']==code for row in catalogue()):
            raise HTTPException(404,'Lot historique introuvable.')
    return {'lot_code':code,'kind':'historical',**qr_payload('historical',code),
            'note':'Dossier historique consultable après authentification. QR ≠ preuve de certification.'}


@router.get('/lots')
def unified_lots(request:Request, search:str=Query('',max_length=100),
                 kind:str=Query('all',pattern='^(all|historical|operational)$'),
                 limit:int=Query(40,ge=1,le=100),offset:int=Query(0,ge=0),
                 user=Depends(require_role('admin'))):
    db=database(request)
    where={}
    if kind!='all':where['kind']=kind
    if search.strip():
        where['$or']=[{k:{'$regex':re.escape(search.strip()),'$options':'i'}}
                      for k in ('code','species','article')]
    total=db.lot_registry.count_documents(where)
    items=list(db.lot_registry.find(where,{'_id':1,'code':1,'kind':1,'species':1,
             'article':1,'varieties':1,'campaign':1,'counts':1,'source':1,'siteCode':1,
             'operationalLotId':1,'linkConfidence':1}).sort('code',1).skip(offset).limit(limit))
    return {'total':total,'items':[{'id':r['_id'],**{k:v for k,v in r.items() if k!='_id'}} for r in items],
            'limit':limit,'offset':offset}


@router.post('/rebuild')
def rebuild_registry(request:Request,user=Depends(require_role('admin'))):
    """Admin repair when migrating older data; idempotent, not called by page views."""
    db=database(request)
    return {'historical_lots':sync_historical_registry(db),
            'operational_lots':sync_operational_registry(db)}
