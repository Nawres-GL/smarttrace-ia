"""Read-only, authenticated proof checks against real Fabric Gateway responses."""
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import authenticated_user, require_role, require_site
from app.fabric_client import FabricBridgeError, read_proof, proof_matches
from app.ledger import verify_local_integrity

router = APIRouter(prefix='/api/blockchain', tags=['Blockchain · Fabric'])


def database(request):
    db = request.app.state.db
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas indisponible.')
    return db


@router.get('/status')
def status(request: Request, user=Depends(require_role('admin'))):
    db = database(request)
    counts = {status: db.blockchain_outbox.count_documents({'status': status})
              for status in ('PENDING','CLAIMED','RETRY','COMMITTED','INVALID_LOCAL')}
    token = os.getenv('FABRIC_BRIDGE_TOKEN', '')
    return {'network_configured': (os.getenv('FABRIC_BRIDGE_URL') in ('http://127.0.0.1:8787', 'http://localhost:8787')
                                   and len(token) >= 32 and not token.startswith('REPLACE_')), 
            'counts': counts,
            'note': 'COMMITTED signifie confirmation rapportée par le worker ; vérifiez un événement pour comparer au registre Fabric.'}


@router.get('/lots/{lot_id}/events/{event_id}/verify')
def verify_lot_event(lot_id: str, event_id: str, request: Request,
                     user=Depends(authenticated_user)):
    db = database(request)
    lot = db.production_lots.find_one({'_id': lot_id})
    if lot is None:
        raise HTTPException(404, 'Lot introuvable.')
    require_site(user, lot['siteCode'])
    event = db.trace_events.find_one({'_id': event_id})
    if event is None:
        raise HTTPException(404, 'Événement non trouvé pour ce lot.')
    # Mirror the exact event relationships shown by the operational lot dossier.
    # A seed reception or graft-related event may belong to a linked parent record.
    details = event.get('details') or {}
    related = ((event.get('subjectType') == 'PRODUCTION_LOT' and event.get('subjectId') == lot_id)
               or (lot.get('seedLotId') is not None
                   and event.get('subjectType') == 'SEED_LOT'
                   and event.get('subjectId') == lot.get('seedLotId'))
               or lot_id in (details.get('parent_lot_ids') or [])
               or details.get('lot_fils_id') == lot_id)
    if not related or event.get('siteCode') != lot['siteCode']:
        raise HTTPException(404, 'Événement non accessible depuis ce lot.')
    local_valid = verify_local_integrity(event)
    if not local_valid:
        return {'status': 'LOCAL_MISMATCH', 'verified': False, 'local_hash_valid': False,
                'tx_id': None}
    try:
        proof = read_proof(event_id)
    except FabricBridgeError:
        return {'status': 'UNAVAILABLE_OR_PENDING', 'verified': False, 'local_hash_valid': True,
                'tx_id': None}
    matched = proof_matches(proof, event)
    return {'status': 'VERIFIED' if matched else 'FABRIC_MISMATCH',
            'verified': matched, 'local_hash_valid': True,
            'tx_id': proof.get('transactionId') if matched else None}
