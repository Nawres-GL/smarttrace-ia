from app.event_utils import canonical_hash

def test_hash_is_stable_for_key_order():
    a = {"schemaVersion": 1, "eventType": "SEMIS", "details": {"quantity": 10}}
    b = {"details": {"quantity": 10}, "eventType": "SEMIS", "schemaVersion": 1}
    assert canonical_hash(a) == canonical_hash(b)

def test_hash_changes_when_data_changes():
    a = {"schemaVersion": 1, "quantity": 10}
    b = {"schemaVersion": 1, "quantity": 11}
    assert canonical_hash(a) != canonical_hash(b)
