"""Deterministic event hashing shared by API and tests."""
import hashlib
import json

def canonical_hash(value: dict) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
