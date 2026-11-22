"""Non-regression tests for V1 local-audit mode."""
from app.ledger import make_event, insert_event, event_public, verify_local_integrity

class DummyCollection:
    def __init__(self): self.inserted=[]
    def insert_one(self, obj, session=None): self.inserted.append(obj)
class DummyDB:
    def __init__(self): self.trace_events=DummyCollection()

def test_event_insert_uses_only_local_journal():
    db=DummyDB()
    event=make_event('PRODUCTION_LOT','lot-1','S01','SEMIS',{'quantity':123},'user-1')
    insert_event(db,event,session=object())
    assert db.trace_events.inserted == [event]
    assert 'blockchainStatus' not in event
    assert verify_local_integrity(event)
    assert event_public(event)['event_hash']==event['eventHash']

def test_event_hash_detects_change():
    event=make_event('PRODUCTION_LOT','lot-1','S01','TRANSFERT',{'quantity':10},'user-1')
    event['details']['quantity']=11
    assert not verify_local_integrity(event)
