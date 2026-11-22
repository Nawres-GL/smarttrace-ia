"""API orchestration regressions on mock data: no Atlas/Fabric/Ollama required."""
import importlib
import sys
import types
import pytest
from fastapi import Response
from pathlib import Path
from test_rag_advanced_v3 import DB

ADMIN = {'role':'admin', 'siteCodes':['S1']}
PROD = {'role':'production', 'siteCodes':['S1']}


@pytest.fixture
def api(monkeypatch):
    """Stub app.auth only for standalone kit; keep real app.auth in a full project."""
    try:
        import app.auth  # noqa: F401
    except ImportError:
        package = types.ModuleType('app')
        package.__path__ = []
        auth = types.ModuleType('app.auth')
        auth.authenticated_user = lambda: None
        monkeypatch.setitem(sys.modules, 'app', package)
        monkeypatch.setitem(sys.modules, 'app.auth', auth)
        importlib.invalidate_caches()
    from rag import api as rag_api
    return rag_api


class FakeRequest:
    def __init__(self, db): self.app = types.SimpleNamespace(state=types.SimpleNamespace(db=db))


def test_ask_delivery_fallback_to_excel_when_mongo_empty(api, monkeypatch):
    from rag import explorer
    monkeypatch.setattr(explorer, '_historical_records', lambda spec: iter([
        {'_id':'e1','source_row':1,'client':'Client X','lot_code':'13877', 'delivery_note_number':'BL100','campaign':'C25'},
        {'_id':'e2','source_row':2,'client':'Client X','lot_code':'12345', 'delivery_note_number':'BL100','campaign':'C25'},
        {'_id':'e3','source_row':3,'client':'Client X','lot_code':'19833', 'delivery_note_number':'BL101','campaign':'C25'},
    ]))
    db = DB()
    db.deliveries.docs = []
    result = api.ask(api.QuestionIn(question='Combien de livraisons par client ?'),
                     FakeRequest(db), Response(), ADMIN)
    assert result['meta']['dataset']=='historical_deliveries'
    assert result['meta']['metric']=='delivery_notes'
    assert result['table']['rows'][0]['value']=='2'
    assert 'historique' in result['summary'].lower()
    assert result['provenance']['source'].startswith('Excel')
    assert result['fallback_from']=='operational_deliveries'


def test_ask_grafting_metric_not_event_count(api, monkeypatch):
    from rag import explorer
    monkeypatch.setattr(explorer,'_historical_records',lambda spec: iter([
        {'source_row':1,'article':'Topgun','lot_code':'12345','grafting_rate_pct':80.},
        {'source_row':2,'article':'Topgun','lot_code':'54321','grafting_rate_pct':90.},
    ]))
    r=api.ask(api.QuestionIn(question='Quel est le taux moyen de greffage par article ?'),
              FakeRequest(DB()),Response(),ADMIN)
    assert r['meta']['dataset']=='historical_grafting'
    assert r['meta']['metric']=='grafting_rate'
    assert r['table']['rows'][0]['value']=='85.0 %'


def test_ask_delivery_two_groupings(api, monkeypatch):
    from rag import explorer
    monkeypatch.setattr(explorer, '_historical_records',lambda spec:iter([
        {'source_row':1,'client':'X','destination_city':'Sousse','unit':'Plants', 'item_quantity':100},
        {'source_row':2,'client':'Y','destination_city':'Sousse','unit':'Plants', 'item_quantity':50},
        {'source_row':3,'client':'X','destination_city':'Sfax','unit':'Plants', 'item_quantity':20},
    ]))
    r=api.ask(api.QuestionIn(question='Quelle quantité a été livrée par client ou par ville ?'),
              FakeRequest(DB()),Response(),ADMIN)
    assert len(r['panels'])==2
    assert {r['panels'][0]['title'],r['panels'][1]['title']} == {'Vue par client','Vue par ville'}
    assert len(r['panels'][1]['result']['rows'])==2


def test_ask_document_quality_without_llm(api, monkeypatch):
    monkeypatch.setenv('RAG_USE_EMBEDDINGS','0')
    monkeypatch.setenv('RAG_USE_OLLAMA','0')
    r=api.ask(api.QuestionIn(question='Comment fonctionne le contrôle qualité avant livraison ?'),
              FakeRequest(DB()),Response(),PROD)
    assert r['route']=='documents' and r['sources']
    assert 'non officiel' in r['sources'][0]['title'].lower() or 'NON OFFICIEL' in r['sources'][0]['title']


def test_nonadmin_no_historical_fallback(api, monkeypatch):
    from rag import explorer
    monkeypatch.setattr(explorer,'_historical_records',lambda spec: (_ for _ in () ))
    db=DB();db.deliveries.docs=[]
    user={'role':'logistique','siteCodes':['S1']}
    r=api.ask(api.QuestionIn(question='Combien de livraisons par client ?'),
              FakeRequest(db),Response(),user)
    assert r['status']=='no_data' and 'fallback_from' not in r
    assert r['meta']['dataset']=='operational_deliveries'


def test_status_reports_document_index(api, monkeypatch):
    monkeypatch.setenv('RAG_USE_EMBEDDINGS','0')
    r=api.status(Response(),ADMIN)
    assert r['documents']['visible_documents']>=2
    assert r['read_only']
