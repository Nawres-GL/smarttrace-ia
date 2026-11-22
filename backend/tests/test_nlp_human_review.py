"""Focused human-review API tests; no Atlas access or trained weights required."""
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
    def __init__(self, rows=()): self.rows = list(rows)
    def find(self, filters, projection):
        key = 'code' if 'code' in filters else 'historicalLotCode'
        match = filters[key]
        sites = filters.get('siteCode', {}).get('$in')
        rows = [r for r in self.rows if r.get(key) == match and (sites is None or r['siteCode'] in sites)]
        return Cursor(rows)
    def find_one(self, filters, projection):
        sites = filters.get('siteCode', {}).get('$in')
        return next((r for r in self.rows if r['_id'] == filters['_id'] and
                     (sites is None or r['siteCode'] in sites)), None)


@pytest.fixture
def nlp_api(monkeypatch):
    auth = ModuleType('app.auth')
    auth.authenticated_user = lambda: None
    monkeypatch.setitem(sys.modules, 'app', ModuleType('app'))
    monkeypatch.setitem(sys.modules, 'app.auth', auth)
    api_path = Path(__file__).resolve().parents[1] / 'nlp' / 'api.py'
    spec = importlib.util.spec_from_file_location('human_review_api', api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(nlp_api, monkeypatch, draft, rows=(), role='admin', text='Germination du lot 13877, 900 plants à 24 degrés.'):
    monkeypatch.setattr(nlp_api, 'parse_draft', lambda _: dict(draft))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(production_lots=Lots(rows)))))
    user = {'role': role, 'siteCodes': ['S01']}
    body = nlp_api.InterpretRequest(text=text)
    return nlp_api.interpret(body, request, user=user)


def example(**extra):
    row = dict(intent='GERMINATION', action='germination',
                fields={'quantity': 900, 'temperature': 24, 'humidity': 80, 'duration_hours': 48},
                lot_reference='13877', missing=['location', 'started_on', 'ended_on', 'observed_on'],
                warnings=[], review_required=False, review_flags=[])
    row.update(extra)
    return row


def test_missing_lot_and_fields_can_open_editor(nlp_api, monkeypatch):
    result = call(nlp_api, monkeypatch, example())
    assert result['ready_for_review'] is True
    assert result['can_open_editor'] is True
    assert result['requires_lot_selection'] is True
    assert result['needs_manual_completion'] is True
    assert result['lot_id'] is None
    assert result['fields']['quantity'] == 900


def test_model_disagreement_is_soft_not_silent_authorization(nlp_api, monkeypatch):
    result = call(nlp_api, monkeypatch, example(review_required=True))
    assert result['ready_for_review'] is True
    assert result['needs_manual_completion'] is True
    assert result['review_required'] is True  # diagnostic remains visible


def test_question_and_negation_are_blocked(nlp_api, monkeypatch):
    for flags in [['NEGATION_OU_ANNULATION'], ['QUESTION_OU_DEMANDE_EXPLICATION'],
                  ['OPERATIONS_MULTIPLES_POSSIBLES']]:
        draft = example()
        draft['review_flags'] = flags
        result = call(nlp_api, monkeypatch, draft)
        assert result['can_open_editor'] is False
        assert result['ready_for_review'] is False


def test_site_scoping_and_single_match(nlp_api, monkeypatch):
    rows = [dict(_id='active-1', code='RO-13877/25', siteCode='S01', historicalLotCode='13877'),
            dict(_id='other-1', code='RO-13877/25', siteCode='S02', historicalLotCode='13877')]
    result = call(nlp_api, monkeypatch, example(), rows=rows, role='production')
    assert result['lot_id'] == 'active-1'
    assert len(result['lot_candidates']) == 1


def test_ambiguous_lot_does_not_auto_select(nlp_api, monkeypatch):
    rows = [dict(_id='a', code='RO-13877/25', historicalLotCode='13877', siteCode='S01'),
            dict(_id='b', code='GRO-G13877/', historicalLotCode='13877', siteCode='S01')]
    result = call(nlp_api, monkeypatch, example(), rows=rows)
    assert result['lot_id'] is None
    assert result['can_open_editor'] is True
    assert result['requires_lot_selection'] is True


def test_role_cannot_perform_unallowed_action(nlp_api, monkeypatch):
    result = call(nlp_api, monkeypatch, example(), role='logistique')
    assert 'germination' not in result['allowed_actions']
    assert 'delivery' in result['allowed_actions']
    assert result['ready_for_review'] is False
    assert result['manual_action_selection_required'] is True


def test_read_only_role_is_rejected(nlp_api, monkeypatch):
    with pytest.raises(Exception) as exc:
        call(nlp_api, monkeypatch, example(), role='lecture')
    assert getattr(exc.value, 'status_code', None) == 403
