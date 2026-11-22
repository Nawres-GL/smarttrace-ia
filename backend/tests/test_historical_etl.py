import unittest
from etl.pipeline import build_matches, lot_five_digits, normalize

class HistoricalETLTests(unittest.TestCase):
    def test_lot_token(self):
        self.assertEqual(lot_five_digits('RO-13766/25'),'13766')
        self.assertEqual(lot_five_digits(13766),'13766')
        self.assertIsNone(lot_five_digits('123456'))

    def test_links_by_lot_only(self):
        p=[{'lot_code':'13766','lot_ref':'RO-13766/25','article':'A','article_key':'A','_id':'p1'}]
        d=[{'_id':'d1','lot_code':'13766','lot_ref_delivery':'13766','article':'B','article_key':'B','source_row':4}]
        x=build_matches(p,d)[0]
        self.assertEqual(x['matching_status'],'LINKED_BY_LOT')
        self.assertTrue(x['article_difference_warning'])
        self.assertEqual(x['matched_production_lot_ref'],'RO-13766/25')
        p.append({'lot_code':'13766','lot_ref':'XX-13766/25','article':'B','article_key':'B','_id':'p2'})
        x=build_matches(p,d)[0]
        self.assertEqual(x['matching_status'],'MULTIPLE_LOT_REFERENCES')
        self.assertEqual(len(x['candidate_lot_refs']),2)

if __name__ == '__main__':unittest.main()
