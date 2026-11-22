"""Local append-only audit events, linked to operational MongoDB transactions.

SHA-256 hashes detect accidental/tampered event changes within local storage,
but are not an independently certified proof.
"""
from datetime import datetime, timezone
from uuid import uuid4
from .event_utils import canonical_hash


def now():
    return datetime.now(timezone.utc)


def make_event(subject_type, subject_id, site, event_type, details, actor_id, occurred_at=None):
    date = occurred_at or now()
    payload = {'schemaVersion': 2, 'eventId': str(uuid4()), 'subjectType': subject_type,
               'subjectId': subject_id, 'siteCode': site, 'eventType': event_type,
               'occurredAt': date.isoformat(), 'actorId': actor_id, 'details': details}
    return {'_id': payload['eventId'], **payload, 'occurredAtDt': date,
            'eventHash': canonical_hash(payload), 'createdBy': actor_id}


def insert_event(db, event, session):
    """Audit event is inserted in the SAME transaction as the business operation.

    No blockchain outbox is created. Older outbox rows in MongoDB are left intact.
    """
    db.trace_events.insert_one(event, session=session)


def event_public(row):
    return {'id': row['_id'], 'event_type': row['eventType'], 'site_code': row['siteCode'],
            'occurred_at': row['occurredAt'], 'actor_id': row.get('actorId', row.get('createdBy')),
            'details': row['details'], 'event_hash': row['eventHash']}


def verify_local_integrity(event):
    """Check local event snapshot consistency. This does NOT query Fabric."""
    keys = ('schemaVersion','eventId','subjectType','subjectId','siteCode',
            'eventType','occurredAt','actorId','details')
    payload = {k: event[k] for k in keys if k in event}
    return canonical_hash(payload) == event.get('eventHash')
