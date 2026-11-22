from datetime import date
from nlp.rules import extract, _date
from nlp.train import validate_split
import pytest


def test_transfer_intent_and_slots():
    r=extract("Aujourd'hui j'ai transféré 500 plants du lot RO-13877/25 de la chambre 2 vers la serre 4.",today=date(2026,11,17))
    assert r['intent']=='TRANSFERT'
    assert r['lot_reference']=='RO-13877/25'
    assert r['fields']=={'quantity':500,'origin':'CHAMBRE-02','destination':'SERRE-04'}
    assert r['missing']==[]


def test_late_stock_and_ambiguity():
    r=extract('Nous avons transféré et livré 300 plants du lot 13877.')
    assert r['intent'] is None
    assert any('Plusieurs' in x for x in r['warnings'])


def test_germination_env():
    r=extract('Germination du lot 13877, 900 plants à 24°C, humidité 80% pendant 48 heures.')
    assert r['fields']['temperature']==24
    assert r['fields']['humidity']==80
    assert r['fields']['duration_hours']==48


def test_stock_loss_requires_reason():
    r=extract('50 plants perdus dans la serre 4 du lot 13877.')
    assert r['intent']=='PERTES'
    assert 'reason' in r['missing']


def test_no_hallucinated_date():
    r=extract('Germination de 200 plants du lot 13877 en chambre 2.')
    assert 'observed_on' not in r['fields']


def test_date_boundaries():
    assert _date('fait le 30/09/2025')=='2025-09-30'
    assert _date("fait aujourd'hui",today=date(2026,11,17))=='2026-11-17'
    assert _date('fait le 31/02/2025') is None


def test_disallowed_duplicate_in_training_split():
    with pytest.raises(ValueError):
        validate_split([{'text':'a','intent':'TRANSFERT'}],[{'text':'a','intent':'TRANSFERT'}],'intent')


def test_no_write_side_effect_in_parser():
    r=extract('Veuillez traiter les plants du lot 13877 dans la serre 5.')
    assert r['action'] in ('treatment',None)
    assert 'status' not in r
