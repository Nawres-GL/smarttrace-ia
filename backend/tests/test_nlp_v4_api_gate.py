"""Updated V4 API behavior: human editor may open with incomplete NLP draft."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


class Cursor:
    def __init__(self, rows): self.rows = rows
    def limit(self, n): return self.rows[:n]


class Lots:
    def find(self, filters, projections):
        key = filters.get('code', filters.get('historicalLotCode'))
        if key in ('RO-54321/25', '17773'):
            return Cursor([{'_id': 'active-1', 'code': key, 'siteCode': 'S01'}])
        return Cursor([])
    def find_one(self, filters, projections):
        return {'_id': 'active-1', 'code': 'RO-54321/25', 'siteCode': 'S01'} if filters['_id'] == 'active-1' else None


@pytest.fixture
def loaded_api(monkeypatch):
    auth = ModuleType('app.auth')
    auth.authenticated_user = lambda: None
    monkeypatch.setitem(sys.modules, 'app', ModuleType('app'))
    monkeypatch.setitem(sys.modules, 'app.auth', auth)
    path = Path(__file__).parents[1] / 'nlp' / 'api.py'
    spec = importlib.util.spec_from_file_location('smarttrace_nlp_api_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(mod, monkeypatch, draft, text):
    monkeypatch.setattr(mod, 'parse_draft', lambda _: draft.copy())
    req = mod.InterpretRequest(text=text)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(production_lots=Lots()))))
    return mod.interpret(req, request, user={'role':'admin','siteCodes':['S01']})


def test_api_blocks_negated_or_multi_operation_draft(monkeypatch, loaded_api):
    draft = {'intent':'TRANSFERT','action':'transfer','fields':{'quantity':60},
             'lot_reference':'17773','missing':['origin','destination'],
             'review_required':True,'warnings':['Opérations multiples'],
             'review_flags':['OPERATIONS_MULTIPLES_POSSIBLES']}
    response = call(loaded_api, monkeypatch, draft,
                    'Transférer 60 plants du lot 17773 et livrer 25 plants demain.')
    assert response['ready_for_review'] is False
    assert response['can_open_editor'] is False


def test_api_allows_missing_fields_and_unresolved_lot_for_review(monkeypatch, loaded_api):
    draft = {'intent':'TRANSFERT','action':'transfer',
             'fields':{'quantity':230, 'origin':'CHAMBRE-01','destination':'SERRE-05'},
             'lot_reference':'RO-00000/25', 'missing':['started_on'],
             'review_required':False,'warnings':[], 'review_flags':[]}
    response = call(loaded_api, monkeypatch, draft,
                    'Transférer 230 plants du lot RO-00000/25 de la chambre 1 vers la serre 5.')
    assert response['ready_for_review'] is True
    assert response['can_open_editor'] is True
    assert response['requires_lot_selection'] is True
    assert response['lot_id'] is None
