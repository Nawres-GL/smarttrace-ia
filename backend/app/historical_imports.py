"""Admin-only incremental Excel import for the three pre-existing SmartTrace projections.

Pilot scope: development environment, MongoDB Atlas-backed history. Originals never modified.
Do not use Excel row position or file digest as a deduplication key: both change on re-export.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import require_role
from etl.pipeline import (make_production_record, make_delivery_record,
                          make_graft_record, digest_file)
from etl.xlsx_reader import headers, rows
from etl.incremental import row_fingerprint, fingerprint_record, preview_plan
from app.correction_review import split_possible_corrections

router = APIRouter(prefix='/api/historique/imports', tags=['Mise à jour Excel'])

SOURCES = {
    'production': ('historical_production_records', make_production_record,
                   {'LOT','Date semis','QteSemis_Rapport','Net_Plants'}),
    'livraison': ('historical_delivery_lines', make_delivery_record,
                 {'N° Lot','Client','N° BOn','Date Effet','Qte'}),
    'greffage': ('historical_grafting_records', make_graft_record,
                 {'Lot_Production','Serre','Taux_Greffage','Net_Plants'}),
}
MAX_BYTES = 30 * 1024 * 1024
MAX_UNCOMPRESSED = 180 * 1024 * 1024
STAGE_DIR = Path(tempfile.gettempdir()) / 'smarttrace_excel_previews'
STAGE_TTL = timedelta(minutes=50)


def utcnow():
    return datetime.now(timezone.utc)


def _db(request):
    db = request.app.state.db
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis pour les mises à jour incrémentales.')
    return db


def _source(kind):
    try:
        return SOURCES[kind]
    except KeyError:
        raise HTTPException(400, 'Type invalide : choisissez production, livraison ou greffage.')



def existing_fingerprints(collection):
    seen = Counter()
    for item in collection.find({}):
        fp = item.get('contentFingerprint')
        if not fp:
            if item.get('source_kind') == 'historical_excel_grafted_production':
                fp = fingerprint_record(item)
            elif item.get('raw_cells'):
                fp = row_fingerprint(item['raw_cells'])
        if fp:
            seen[fp] += 1
        for accepted in set(item.get("acceptedContentFingerprints") or []):
            if accepted != fp: seen[accepted] += 1
    return seen



def _parse_file(path, kind):
    collection_name, factory, required = _source(kind)
    try:
        with ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_UNCOMPRESSED:
                raise HTTPException(413, 'Fichier Excel décompressé trop volumineux.')
            if not archive.testzip() is None:
                raise HTTPException(422, 'Archive Excel endommagée.')
        file_headers = headers(path)
        missing = sorted(required.difference(file_headers))
        if missing:
            raise HTTPException(422, 'Colonnes attendues manquantes : ' + ', '.join(missing))
        file_hash = digest_file(path)
        records = [factory(row, file_hash) for row in rows(path)]
        if not records:
            raise HTTPException(422, 'Le fichier ne contient aucune ligne de données.')
        return collection_name, file_headers, file_hash, records
    except (BadZipFile, KeyError, ValueError, IndexError) as ex:
        raise HTTPException(422, 'Fichier .xlsx non reconnu ou structure non prise en charge.') from ex


def _validate_schema(db, kind, file_headers):
    config = db.historical_import_schemas.find_one({'_id': kind})
    if config and config.get('columns') != file_headers:
        raise HTTPException(422, 'Les colonnes doivent être exactement celles du modèle validé, dans le même ordre. Import annulé.')


def _cleanup():
    if not STAGE_DIR.exists():
        return
    threshold = utcnow().timestamp() - STAGE_TTL.total_seconds()
    for file in list(STAGE_DIR.glob('*.xlsx')) + list(STAGE_DIR.glob('*.json')):
        if file.stat().st_mtime < threshold:
            file.unlink(missing_ok=True)


@router.post('/{kind}/preview')
async def preview(kind: str, request: Request, user=Depends(require_role('admin'))):
    db = _db(request)
    _source(kind)
    if request.headers.get('content-type','').split(';')[0].strip() not in {
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/octet-stream'}:
        raise HTTPException(415, 'Transmettez uniquement un fichier .xlsx.')
    STAGE_DIR.mkdir(mode=0o700, exist_ok=True)
    _cleanup()
    stage_id = uuid.uuid4().hex
    temp = STAGE_DIR / (stage_id + '.xlsx')
    metadata_path = STAGE_DIR / (stage_id + '.json')
    length = 0
    try:
        with temp.open('xb') as fh:
            async for chunk in request.stream():
                length += len(chunk)
                if length > MAX_BYTES:
                    raise HTTPException(413, 'Fichier trop volumineux (maximum 30 Mo).')
                fh.write(chunk)
        _, schema, file_hash, records = _parse_file(temp, kind)
        _validate_schema(db, kind, schema)
        collection_name = SOURCES[kind][0]
        seen = existing_fingerprints(db[collection_name])
        stats, additions = preview_plan(records, seen)
        safe_new, possible_edits = split_possible_corrections(kind, additions,
                                         list(db[collection_name].find({})))
        occurrences = Counter()
        old_sample = []
        for rec in records:
            fp = fingerprint_record(rec)
            occurrences[fp] += 1
            if occurrences[fp] <= seen[fp] and len(old_sample) < 8:
                old_sample.append(rec.get('source_row'))
        # Preview belongs to its uploader and source type, not any other admin.
        metadata_path.write_text(json.dumps({
            'user': str(user['_id']), 'kind': kind, 'sha256': file_hash,
            'received_rows': stats['total'], 'new_rows': stats['new'],
            'duplicate_rows': stats['duplicates'],
            'safe_new_rows':len(safe_new),'review_rows':len(possible_edits)
        }), encoding='utf-8')
        new_lots = sorted({str(r.get('lot_code')) for r in safe_new if r.get('lot_code')})
        return {'preview_id': stage_id, 'kind': kind, 'file_sha256': file_hash,
                'received_rows': stats['total'], 'duplicate_rows': stats['duplicates'],
                'new_rows': len(safe_new), 'possible_corrections': len(possible_edits),
                'sample_possible_corrections':[{'excel_row':x['source_row'],
                    'lot_code':x['lot_code'],'differences':x['differences'],'ambiguous':x['ambiguous']} for x in possible_edits[:5]],
                'new_lot_codes': len(new_lots),
                'sample_new_lots': new_lots[:8],
                'sample_new_source_rows': [r.get('source_row') for r in safe_new[:8]],
                'sample_existing_source_rows': old_sample, 'resulting_rows': db[collection_name].count_documents({}) + len(safe_new),
                'source_mode': os.getenv('HISTORY_MODE','excel').lower(),
                'notice': 'Aucun changement effectué. Les modifications de lignes existantes sont à examiner avant de confirmer.'}
    except Exception:
        temp.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise


@router.post('/{kind}/confirm/{preview_id}')
def confirm(kind: str, preview_id: str, request: Request, user=Depends(require_role('admin'))):
    db = _db(request)
    _source(kind)
    if not len(preview_id) == 32 or any(c not in '0123456789abcdef' for c in preview_id):
        raise HTTPException(400, 'Identifiant de prévisualisation incorrect.')
    path = STAGE_DIR / (preview_id + '.xlsx')
    if not path.is_file() or utcnow().timestamp() - path.stat().st_mtime > STAGE_TTL.total_seconds():
        raise HTTPException(410, 'Prévisualisation expirée. Rechargez le fichier.')
    meta_path = STAGE_DIR / (preview_id + '.json')
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        raise HTTPException(410, 'Prévisualisation invalide ou expirée. Relancez une analyse.')
    if meta.get('user') != str(user['_id']) or meta.get('kind') != kind:
        raise HTTPException(403, 'Cette prévisualisation appartient à un autre utilisateur ou une autre source.')
    collection_name, schema, file_hash, records = _parse_file(path, kind)
    if file_hash != meta.get('sha256'):
        raise HTTPException(409, 'Le fichier a changé depuis la prévisualisation. Réanalysez-le.')
    _validate_schema(db, kind, schema)
    from pymongo import InsertOne
    from pymongo.errors import BulkWriteError
    collection = db[collection_name]
    stats, additions = preview_plan(records, existing_fingerprints(collection))
    if any(stats[k] != meta.get({'total':'received_rows','new':'new_rows','duplicates':'duplicate_rows'}[k])
           for k in ('total','new','duplicates')):
        raise HTTPException(409, 'Les données ont changé depuis la prévisualisation. Réanalysez avant de confirmer.')
    safe_new, possible_edits = split_possible_corrections(kind, additions,
                                        list(collection.find({})))
    if len(safe_new)!=meta.get('safe_new_rows') or len(possible_edits)!=meta.get('review_rows'):
        raise HTTPException(409,'Les propositions de correction ont changé. Réanalysez le fichier.')
    actually_added = 0
    try:
        for i in range(0, len(safe_new), 300):
            batch = safe_new[i:i+300]
            try:
                result = collection.bulk_write([InsertOne(row) for row in batch], ordered=False)
                actually_added += result.inserted_count
            except BulkWriteError as exc:
                errors = exc.details.get('writeErrors', [])
                if any(err.get('code') != 11000 for err in errors):
                    raise
                actually_added += exc.details.get('nInserted', 0)
        for candidate in possible_edits:
            new=candidate['new_record']
            key='review:'+kind+':'+str(candidate['original_id'])+':'+new['contentFingerprint']
            db.historical_correction_reviews.update_one({'_id':key},
                {'$setOnInsert':{'kind':kind,'status':'PENDING',
                  'originalId':candidate['original_id'],'sourceRow':candidate['source_row'],
                  'lotCode':candidate['lot_code'],'differences':candidate['differences'],
                  'newRecord':new,'ambiguous':candidate['ambiguous'],
                  'reason':candidate['reason'],'createdAt':utcnow(),'submittedBy':str(user['_id']),
                  'batchId':preview_id}},upsert=True)
        db.historical_import_schemas.update_one({'_id': kind}, {'$setOnInsert': {
            'columns': schema, 'createdAt': utcnow()}}, upsert=True)
        db.historical_import_batches.insert_one({'_id': preview_id, 'kind': kind,
            'fileHash': file_hash, 'submittedBy': user['_id'], 'createdAt': utcnow(),
            'receivedRows': stats['total'], 'duplicateRows': stats['duplicates'],
            'addedRows': actually_added, 'reviewRows':len(possible_edits)})
    finally:
        path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    from app.unified_registry import sync_historical_registry
    # Refresh just the new lot codes; same five-digit code across sources is only a candidate link.
    sync_historical_registry(db, {row.get('lot_code') for row in safe_new})
    from app.history import from_excel
    from_excel.cache_clear()
    return {'kind': kind, 'added_rows': actually_added,
            'duplicate_rows': stats['duplicates'], 'possible_corrections':len(possible_edits),
            'total_rows': collection.count_documents({}),
            'source_mode': os.getenv('HISTORY_MODE','excel').lower(),
            'message': 'Lignes nouvelles ajoutées ; corrections suspectées mises en attente de revue. Sources Excel inchangées.'}


@router.get('/status')
def status(request: Request, user=Depends(require_role('admin'))):
    db = _db(request)
    return {'source_mode': os.getenv('HISTORY_MODE','excel').lower(),
            'counts': {kind: db[collection].count_documents({}) for kind,(collection,*_) in SOURCES.items()},
            'recent': [{k:v for k,v in item.items() if k != '_id'} for item in
              db.historical_import_batches.find({}).sort('createdAt', -1).limit(5)]}
