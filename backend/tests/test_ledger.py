"""Tests du noyau d’audit, sans accès Atlas et sans modifier Excel."""
import unittest
from app.ledger import make_event, verify_local_integrity

class LedgerTests(unittest.TestCase):
    def test_actor_and_hash_are_recorded(self):
        ev=make_event('PRODUCTION_LOT','L01','S01','TRANSFERT',{'quantity':10},'USER-01')
        self.assertTrue(verify_local_integrity(ev))
        self.assertEqual(ev['actorId'],'USER-01')
        self.assertIn('eventHash', ev)
        self.assertNotIn('blockchainStatus', ev)

    def test_tampered_detail_fails(self):
        ev=make_event('PRODUCTION_LOT','L01','S01','LIVRAISON',{'quantity':10},'USER-01')
        ev['details']['quantity']=20
        self.assertFalse(verify_local_integrity(ev))

if __name__=='__main__':unittest.main()
