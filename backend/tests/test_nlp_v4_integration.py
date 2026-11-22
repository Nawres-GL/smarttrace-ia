"""Offline tests of V4 integration. No PyTorch, MongoDB, or exported weights required."""
import sys
from types import SimpleNamespace

from nlp.service import _identifier, _location, parse_draft
from nlp.safety_guard import assess_instruction


def mock_predict(monkeypatch, label, score, entities=()):
    monkeypatch.setenv('NLP_MODE', 'hybrid')
    monkeypatch.setenv('NLP_MIN_INTENT_SCORE', '0.45')
    monkeypatch.setenv('NLP_MIN_ENTITY_SCORE', '0.45')
    monkeypatch.setitem(sys.modules, 'nlp.transformer', SimpleNamespace(
        predict=lambda text: {'intent': label, 'intent_score': score,
                              'intent_alternatives': [{'label': label, 'score': score}],
                              'entities': list(entities)}
    ))


def span(label, text, score):
    return {'label': label, 'text': text, 'start': 0, 'end': len(text), 'score': score}


def test_v4_transfer_uses_rules_for_weak_origin_destination(monkeypatch):
    mock_predict(monkeypatch, 'TRANSFERT', .566, [span('ORIGIN', 'chambre 1', .406),
                                                  span('DESTINATION', 'serre 5', .419)])
    r = parse_draft('Nous avons déplacé 230 plants du lot RO-54321/25 de la chambre 1 vers la serre 5.')
    assert r['action'] == 'transfer'
    assert r['fields'] == {'quantity': 230, 'origin': 'CHAMBRE-01', 'destination': 'SERRE-05'}
    assert r['nlp_thresholds'] == {'intent': .45, 'entity': .45}
    assert not r['review_required']


def test_supplier_and_variety_from_v4_ner(monkeypatch):
    mock_predict(monkeypatch, 'RECEPTION_SEMENCES', .588, [span('SUPPLIER', 'Client Gamma', .506),
                                                            span('VARIETY', 'tomate Roma', .608)])
    r = parse_draft('Réception de 2 400 graines de tomate Roma du fournisseur Client Gamma.')
    assert r['action'] == 'seed'
    assert r['fields']['quantity_received'] == 2400
    assert r['fields']['supplier'] == 'Client Gamma'
    assert r['fields']['variety'] == 'tomate Roma'
    assert 'species' in r['missing']  # Never silently confuse species and variety.


def test_punctuation_and_tray_codes(monkeypatch):
    mock_predict(monkeypatch, 'SEMIS', .617, [span('TRAY', 'plateau P104.', .50),
                                               span('LOT', 'RO-55661/26.', .90)])
    r = parse_draft('Semer 450 graines du lot RO-55661/26 sur plateau P104.')
    assert r['fields']['tray_type'] == 'P104'
    assert r['lot_reference'] == 'RO-55661/26'
    assert _identifier('88231.') == '88231'


def test_bl_fallback_despite_wrong_ner_label(monkeypatch):
    mock_predict(monkeypatch, 'LIVRAISON', .568, [span('ROOTSTOCK_LOT', 'BL-DEMO-556', .60)])
    r = parse_draft('Livrer 840 plants du lot RO-98314/25 pour Client Exemple, bon BL-DEMO-556.')
    assert r['action'] == 'delivery'
    assert r['fields']['delivery_note'] == 'BL-DEMO-556'
    assert 'rootstock_lot_id' not in r['fields']


def test_explicit_hors_sujet_blocks(monkeypatch):
    mock_predict(monkeypatch, 'HORS_SUJET', .50)
    r = parse_draft('Ne transférez pas 500 plants du lot RO-13777/25.')
    assert r['action'] is None
    assert r['review_required']
    assert 'NEGATION_OU_ANNULATION' in r['review_flags']


def test_multiple_operations_remain_blocked(monkeypatch):
    mock_predict(monkeypatch, 'HORS_SUJET', .49)
    r = parse_draft('Transférer 60 plants du lot 17773 vers serre 7 et livrer 25 plants demain.')
    assert r['review_required']
    assert 'OPERATIONS_MULTIPLES_POSSIBLES' in r['review_flags']


def test_low_score_disagreement_blocks_even_with_rule_guess(monkeypatch):
    mock_predict(monkeypatch, 'TRANSFERT', .336)
    r = parse_draft('La chambre de germination accueille 1 200 plantules du lot 28791.')
    assert r['action'] == 'germination'
    assert r['review_required']
    assert any('Désaccord' in x for x in r['warnings'])


def test_high_score_disagreement_blocks(monkeypatch):
    mock_predict(monkeypatch, 'PERTES', .58)
    r = parse_draft('Nous avons déplacé 230 plants du lot RO-54321/25 de la chambre 1 vers la serre 5.')
    assert r['review_required']


def test_invalid_fragment_cannot_override_complete_origin(monkeypatch):
    mock_predict(monkeypatch, 'TRANSFERT', .6, [span('ORIGIN', '1', .98)])
    r = parse_draft('Transférer 230 plants du lot 54321 de la chambre 1 vers la serre 5.')
    assert r['fields']['origin'] == 'CHAMBRE-01'


def test_normalization_is_strict():
    assert _location('serre 5') == 'SERRE-05'
    assert _location('zone C') == 'ZONE_C'
    assert _location('chambre froide') == 'CHAMBRE_FROIDE'
    assert _location('1') is None
    assert _location('un site non identifié') is None
    assert assess_instruction('Comment transférer 300 plants ?')['status'] == 'REQUIRES_REVIEW'
