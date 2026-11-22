"""Run from backend: python -m pytest tests/test_rag_advanced_v3.py -q"""
import os
import sys
from pathlib import Path
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from rag.catalog import CATALOG, public_catalog
from rag.explorer import explore, ForbiddenExplore, InvalidExplore
from rag.planner import maybe_plan
from rag.documents import search_documents

ADMIN = {'role':'admin','siteCodes':['S1']}
PROD = {'role':'production','siteCodes':['S1']}
LOGIS = {'role':'logistique','siteCodes':['S1']}


class Cursor:
    def __init__(self, docs): self.docs = docs
    def limit(self, n): return self.docs[:n]
    def __iter__(self): return iter(self.docs)


class Collection:
    def __init__(self, docs): self.docs = docs
    def find(self, query=None, projection=None):
        query = query or {}
        def match(row):
            for k, condition in query.items():
                if isinstance(condition, dict) and '$in' in condition:
                    if row.get(k) not in condition['$in']: return False
                elif row.get(k) != condition: return False
            return True
        return Cursor([dict(d) for d in self.docs if match(d)])


class DB:
    def __init__(self):
        self.production_lots = Collection([
            {'_id':'l1','code':'13877','siteCode':'S1','campaign':'C25','species':'TOMATE',
             'variety':'Roma','quantitySown':100,'plantsLost':40,'plantsInStock':60,
             'plantsDelivered':0,'qualityStatus':'CONFORME'},
            {'_id':'l2','code':'19833','siteCode':'S1','campaign':'C25','species':'TOMATE',
             'variety':'Roma','quantitySown':300,'plantsLost':30,'plantsInStock':270,
             'plantsDelivered':0,'qualityStatus':'NON_CONTROLE'},
            {'_id':'SECRET','code':'99999','siteCode':'S2','campaign':'C25','species':'TOMATE',
             'variety':'X','quantitySown':50,'plantsLost':49,'plantsInStock':1},
        ])
        self.preparations = Collection([
            {'_id':'p1','siteCode':'S1','lotId':'l1','client':'A','quantityReserved':80,'quantityDelivered':50},
            {'_id':'p2','siteCode':'S2','lotId':'SECRET','client':'Private','quantityReserved':3000,'quantityDelivered':0},
        ])
        self.deliveries = Collection([
            {'_id':'d1','siteCode':'S1','lotId':'l1','client':'Client X','quantity':120,'date':'2025-05-08'},
            {'_id':'d2','siteCode':'S1','lotId':'l2','client':'Client Y','quantity':80,'date':'2025-05-09'},
            {'_id':'d3','siteCode':'S2','lotId':'SECRET','client':'Private','quantity':5000,'date':'2025-05-10'},
        ])
        self.trace_events = Collection([{'_id':'e1','siteCode':'S1','eventType':'GREFFAGE'},
                                        {'_id':'e2','siteCode':'S2','eventType':'SECRET'}])


def test_catalog_hides_historical_and_customers_from_non_admin():
    ids = {x['id'] for x in public_catalog(PROD)['datasets']}
    assert 'historical_production' not in ids
    assert 'operational_deliveries' not in ids
    assert 'operational_lots' in ids


def test_forbidden_historical_for_employee():
    with pytest.raises(ForbiddenExplore):
        explore('historical_production','records',None,{},PROD,DB())


def test_site_scope_applied_before_aggregation():
    r = explore('operational_lots','records',None,{},PROD,DB())
    assert r['meta']['matching_records'] == 2
    assert '99999' not in r['answer']
    assert '2 (' in r['answer']


def test_site_filter_cannot_escalate():
    with pytest.raises(ForbiddenExplore):
        explore('operational_lots','records',None,{'site':'S2'},PROD,DB())


def test_weighted_loss_ratio_not_simple_mean():
    r = explore('operational_lots','loss_rate',None,{'campaign':'C25'},PROD,DB())
    # (40+30) / (100+300) = 17.5%, not 25% (simple average of rates).
    assert '17.5 %' in r['answer']


def test_numeric_threshold_applied_to_each_lot():
    r = explore('operational_lots','loss_rate','lot_code',{},PROD,DB(),threshold=30)
    assert '13877' in r['answer']
    assert '19833' not in r['answer']


def test_logistics_pending_respects_site():
    r = explore('operational_preparations','pending',None,{},LOGIS,DB())
    assert '30' in r['answer']
    assert '3 000' not in r['answer']


def test_delivery_grouping_and_pagination():
    first = explore('operational_deliveries','quantity','client',{},LOGIS,DB(),limit=1)
    assert first['meta']['total_groups'] == 2
    second = explore('operational_deliveries','quantity','client',{},LOGIS,DB(),limit=1,offset=1)
    assert second['meta']['offset'] == 1
    assert first['sources'][0]['title'] != second['sources'][0]['title']


def test_operator_injection_rejected():
    with pytest.raises(InvalidExplore):
        explore('operational_lots','records',None,{'siteCode':{'$ne':'S1'}},PROD,DB())


def test_unknown_collection_rejected():
    with pytest.raises(InvalidExplore):
        explore('users','records',None,{},ADMIN,DB())


def test_planner_tomato_germination_history_admin():
    p = maybe_plan('Compare les taux de germination des variétés de tomates pour la campagne C25.', 'admin')
    assert p.dataset == 'historical_production'
    assert p.metric == 'germination_rate'
    assert p.group_by == 'variety'
    assert p.filters == {'campaign':'C25','species':'tomate'}


def test_planner_does_not_override_procedure():
    assert maybe_plan('Quelles sont les étapes du contrôle qualité avant livraison ?', 'admin') is None


def test_planner_client_deliveries():
    p = maybe_plan('Quelle quantité a été livrée par client pendant C25 ?', 'admin')
    assert p.dataset == 'historical_deliveries'
    assert p.metric == 'item_quantity'
    assert p.group_by == 'client'


def test_planner_preparations_not_deliveries():
    p = maybe_plan('Quelles préparations restent à livrer ?', 'logistique')
    assert p.dataset == 'operational_preparations'
    assert p.metric == 'pending'


def test_document_retrieval_works_without_embeddings(monkeypatch):
    monkeypatch.setenv('RAG_USE_EMBEDDINGS','0')
    doc_root = BACKEND / 'rag_documents'
    docs, mode = search_documents('Quelles sont les étapes du contrôle qualité avant livraison ?', PROD, root=doc_root)
    assert docs
    assert any('qualit' in item.title.lower() for item,_ in docs)
    assert mode == 'lexical'


def test_historical_metric_unit_partition(monkeypatch):
    # Mock the pre-indexed historical readers; no actual customer Excel required.
    from rag import explorer
    rows = [
        {'source_row':1,'lot_code':'13877','item_quantity':20,'unit':'PCE','campaign':'C25','client':'X'},
        {'source_row':2,'lot_code':'13877','item_quantity':40,'unit':'Pltx 40 POLY','campaign':'C25','client':'X'},
    ]
    monkeypatch.setattr(explorer, '_historical_records', lambda spec: iter(rows))
    r = explore('historical_deliveries','item_quantity','client',{'campaign':'C25'},ADMIN,DB())
    assert r['meta']['total_groups'] == 2
    assert any('unit' in s['group'] for s in r['sources'])


def test_historical_distinct_codes_and_rows_not_confused(monkeypatch):
    from rag import explorer
    rows=[{'source_row':1,'lot_code':'12345','total_loss_pct':70,'campaign':'C25'},
          {'source_row':2,'lot_code':'12345','total_loss_pct':70,'campaign':'C25'},
          {'source_row':3,'lot_code':'45678','total_loss_pct':30,'campaign':'C25'}]
    monkeypatch.setattr(explorer,'_historical_records', lambda spec: iter(rows))
    a = explore('historical_grafting','records',None,{},ADMIN,DB())
    b = explore('historical_grafting','lots',None,{},ADMIN,DB())
    assert '3 (' in a['answer']
    assert '2 (' in b['answer']


def test_historical_weighted_germination_and_bad_rate(monkeypatch):
    from rag import explorer
    rows=[{'source_row':1,'lot_code':'12345','variety':'Roma','seeds_sown':100,'germination_rate_pct':80},
          {'source_row':2,'lot_code':'54321','variety':'Roma','seeds_sown':300,'germination_rate_pct':100},
          {'source_row':3,'lot_code':'67890','variety':'Roma','seeds_sown':50,'germination_rate_pct':135}]
    monkeypatch.setattr(explorer,'_historical_records', lambda spec: iter(rows))
    r = explore('historical_production','germination_rate','variety',{},ADMIN,DB())
    assert '95.0 %' in r['answer']
    assert 'ignorée(s)' in r['answer']


def test_planner_operational_germination_without_campaign():
    p = maybe_plan('Compare les taux de germination par variété.', 'production')
    assert p.dataset == 'operational_germination'
    assert p.metric == 'germination_rate'
    assert p.group_by == 'variety'


def test_operational_germination_weighted_and_site_scoped():
    db = DB()
    db.production_lots.docs[0]['lotType'] = 'SEMIS'
    db.production_lots.docs[1]['lotType'] = 'SEMIS'
    db.trace_events.docs.extend([
        {'_id':'g1','siteCode':'S1','subjectId':'l1','subjectType':'PRODUCTION_LOT',
         'eventType':'GERMINATION','details':{'quantite_semee':100,'quantite_germee':50}},
        {'_id':'g2','siteCode':'S1','subjectId':'l2','subjectType':'PRODUCTION_LOT',
         'eventType':'GERMINATION','details':{'quantite_semee':300,'quantite_germee':270}},
        {'_id':'gSecret','siteCode':'S2','subjectId':'SECRET','subjectType':'PRODUCTION_LOT',
         'eventType':'GERMINATION','details':{'quantite_semee':50,'quantite_germee':50}},
    ])
    r = explore('operational_germination','germination_rate','variety',{},PROD,db)
    assert '80.0 %' in r['answer']
    assert 'gSecret' not in r['answer']
    assert r['meta']['matching_records'] == 2


def test_month_filter_and_grouping():
    r = explore('operational_deliveries','quantity','month',{'month':'2025-05'},LOGIS,DB())
    assert '2025-05' in r['answer']
    assert '200 (' in r['answer']


def test_delivery_group_by_lot_code_uses_authorized_real_code():
    r = explore('operational_deliveries','quantity','lot_code',{},LOGIS,DB())
    assert '13877' in r['answer']
    assert '19833' in r['answer']
    assert 'SECRET' not in r['answer']
