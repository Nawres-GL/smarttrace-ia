"""Manual/dev worker: auditable outbox -> Fabric, no historical Excel data.

Run only when MongoDB, the Fabric network, chaincode and local Go bridge are ready.
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument
from app.fabric_client import FabricBridgeError, proof_matches, read_proof, submit_proof
from app.ledger import verify_local_integrity


def utcnow():
    return datetime.now(timezone.utc)


def claim(db):
    now = utcnow()
    return db.blockchain_outbox.find_one_and_update(
        {'$or': [{'status': {'$in': ['PENDING', 'RETRY']}, 'nextAttemptAt': {'$lte': now}},
                 {'status': {'$in': ['PENDING', 'RETRY']}, 'nextAttemptAt': {'$exists': False}},
                 {'status': 'CLAIMED', 'leaseUntil': {'$lte': now}}]},
        {'$set': {'status': 'CLAIMED', 'leaseUntil': now + timedelta(minutes=3),
                  'claimedAt': now}, '$inc': {'attempts': 1}},
        sort=[('createdAt', 1)], return_document=ReturnDocument.AFTER)


def run_once(db):
    job = claim(db)
    if not job:
        return False
    event_id = job['_id']
    event = db.trace_events.find_one({'_id': event_id})
    if event is None or not verify_local_integrity(event) or event.get('eventHash') != job.get('eventHash'):
        db.blockchain_outbox.update_one({'_id': event_id, 'status': 'CLAIMED'},
                                         {'$set': {'status': 'INVALID_LOCAL', 'updatedAt': utcnow()}, '$unset': {'leaseUntil': ''}})
        print('INVALID_LOCAL: stored event hash did not match; manual review required')
        return True
    try:
        # Recheck first: a previous submission may have committed before its response was lost.
        try:
            proof = read_proof(event_id)
            if not proof_matches(proof, event):
                raise FabricBridgeError('La preuve existante ne correspond pas à cet événement.')
        except FabricBridgeError:
            proof = submit_proof(event)
        # Verify AGAIN from the independent Fabric query, not only the POST response.
        proof = read_proof(event_id)
        if not proof_matches(proof, event):
            raise FabricBridgeError('La preuve consultée sur Fabric ne correspond pas à cet événement.')
        tx_id = proof['transactionId']
        # Make the event visible as confirmed before finalizing outbox status. On crash,
        # expired CLAIMED leases will recover idempotently by reading the existing proof.
        db.trace_events.update_one({'_id': event_id}, {'$set': {
            'blockchainStatus': 'VERIFIE', 'blockchainTxId': tx_id,
            'certifiedAt': utcnow()}})
        db.blockchain_outbox.update_one({'_id': event_id, 'status': 'CLAIMED'}, {
            '$set': {'status': 'COMMITTED', 'transactionId': tx_id,
                     'updatedAt': utcnow()}, '$unset': {'leaseUntil': '', 'nextAttemptAt': ''}})
        print('COMMITTED event=' + event_id + ' tx=' + tx_id)
    except FabricBridgeError:
        attempts = job.get('attempts', 1)
        next_attempt = utcnow() + timedelta(seconds=min(30 * (2 ** min(attempts, 6)), 3600))
        db.blockchain_outbox.update_one({'_id': event_id, 'status': 'CLAIMED'}, {
            '$set': {'status': 'RETRY', 'updatedAt': utcnow(),
                     'nextAttemptAt': next_attempt}, '$unset': {'leaseUntil': ''}})
        print('RETRY event=' + event_id + ' (Fabric unavailable or not confirmed)')
    return True


def main():
    parser = argparse.ArgumentParser(description='Royal Plants SmartTrace Fabric outbox worker')
    parser.add_argument('--loop', action='store_true', help='Keep polling; stop with Ctrl+C')
    args = parser.parse_args()
    load_dotenv()
    if os.getenv('APP_ENV') != 'development':
        raise SystemExit('Pilot worker only: production deployment must be reviewed.')
    uri, name = os.getenv('MONGODB_URI'), os.getenv('MONGODB_DB', 'royal_plants_smarttrace_dev')
    if not uri:
        raise SystemExit('Configure MONGODB_URI in backend/.env')
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command('ping')
        db = client[name]
        if args.loop:
            print('Worker active. Ctrl+C to stop.')
            while True:
                if not run_once(db):
                    time.sleep(3)
        else:
            if not run_once(db):
                print('No pending Fabric events.')
    except KeyboardInterrupt:
        print('Worker stopped.')
    finally:
        client.close()


if __name__ == '__main__':
    main()
