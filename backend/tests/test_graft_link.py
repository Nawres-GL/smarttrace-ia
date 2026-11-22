from pathlib import Path
from etl.pipeline import lot_five_digits, make_graft_record
from app.history import summarize, safe_grafting


def test_gro_lot_extraction():
    assert lot_five_digits('GRO-G13877/') == '13877'
    assert lot_five_digits('RO-13877/25') == '13877'
    assert lot_five_digits(13877) == '13877'


def test_graft_record_and_merge():
    record = make_graft_record({'excel_row': 2, 'fields': {
        'LOT':'GRO-G13877/', 'Lot_Production': 13877, 'Article': 'Topgun/Matrix',
        'Serre':'SERRE EN BOIS 2','Taux_Greffage':95.65,'Perte_Greffage':4.35}},'abcdef1234567890')
    assert record['lot_code']=='13877'
    assert record['grafting_rate_pct']==95.65
    summary = summarize('13877', [{'lot_ref':'RO-13877/25','article':'Topgun','article_key':'TOPGUN','variety':'Topgun'}],[],[record])
    assert summary['grafting_rows']==1
    assert safe_grafting(record)['greenhouse']=='SERRE EN BOIS 2'
