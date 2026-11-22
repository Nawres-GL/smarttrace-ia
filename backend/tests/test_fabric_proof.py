import unittest
from unittest.mock import patch
from app.ledger import make_event, verify_local_integrity
from app.fabric_client import proof_matches, FabricBridgeError, _settings

class FabricProofTests(unittest.TestCase):
    def test_matches_real_event(self):
        ev = make_event('PRODUCTION_LOT','L01','S01','TRANSFERT',{'qty':10},'U01')
        proof = {'eventId':ev['_id'],'subjectId':ev['subjectId'],
                 'eventType':ev['eventType'],'eventHash':ev['eventHash'],'transactionId':'tx123'}
        self.assertTrue(verify_local_integrity(ev))
        self.assertTrue(proof_matches(proof,ev))
        proof['eventHash'] = 'f' * 64
        self.assertFalse(proof_matches(proof,ev))

    def test_unconfigured_bridge_is_rejected(self):
        with patch.dict('os.environ', {'FABRIC_BRIDGE_URL':'http://some-random-server','FABRIC_BRIDGE_TOKEN':'1234567890abcdef1234567890abcdef'}):
            with self.assertRaises(FabricBridgeError):
                _settings()
