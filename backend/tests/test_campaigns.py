from app.campaigns import campaign_for_date, campaign_bounds, inferred_lot_campaign
from app.history import summarize, filtered_catalogue


def test_boundaries():
    assert campaign_bounds('C25')[0].isoformat() == '2024-10-01'
    assert campaign_bounds('C25')[1].isoformat() == '2025-09-30'
    assert campaign_for_date('2024-09-30') == 'C24'
    assert campaign_for_date('2024-10-01') == 'C25'
    assert campaign_for_date('2025-09-30') == 'C25'
    assert campaign_for_date('2025-10-01') == 'C26'
    assert campaign_for_date('2024-12-02') == 'C25'


def test_production_date_has_priority_over_delivery_date():
    p = [{'sowing_date':'2025-09-30'}]
    d = [{'document_date':'2025-10-01'}]
    assert inferred_lot_campaign(p, [], d) == ('C25', 'date_semis')
    assert inferred_lot_campaign([], [], d) == ('C26', 'date_document_livraison')
    assert inferred_lot_campaign([{'sowing_date': '2025-09-30'}, {'sowing_date': '2025-10-01'}], [], d) == (None,'dates_contradictoires')


def test_taxonomy_classification_respects_production_and_normalizes_case():
    p=[{'lot_ref':'RO-13766/25','species':'AUBERGINE','article':'A336 F1','variety':'A336 F1','article_key':'A336 F1','sowing_date':'2025-03-27'}]
    g=[{'lot_ref':'GRO-G13766/','species':'Aubergine','article':'Grafted A336','variety':'Grafted A336'}]
    d=[{'species':'Aubergine','article':'Other article','article_key':'OTHER','document_date':'2025-04-29'}]
    row=summarize('13766',p,d,g)
    assert row['species']==['Aubergine']
    assert row['articles']==['A336 F1']
    assert row['article_difference_count'] == 1
    assert row['campaign']=='C25'
    assert filtered_catalogue([row],campaign='C25',species='Aubergine',article='A336 F1') == [row]
    assert filtered_catalogue([row],campaign='C26') == []
