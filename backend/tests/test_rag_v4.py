"""Offline Phase 7 V4 regression tests. Run from backend with pytest."""
from pathlib import Path
import pytest

from rag.planner import maybe_plan, Plan
from rag.source_selection import alternative_for_empty, fallback_notice
from rag.presentation import present_explore
from rag.explorer import explore
from rag.documents import document_status, search_documents
from rag.llm_planner import validate_plan, allowed_catalog_summary

ADMIN = {'role': 'admin', 'siteCodes': ['S1']}
PROD = {'role': 'production', 'siteCodes': ['S1']}
HERE = Path(__file__).resolve().parents[1]


def test_graft_rate_not_event_count():
    p = maybe_plan('Quel est le taux moyen de greffage par article ?', 'admin')
    assert (p.dataset, p.metric, p.group_by) == ('historical_grafting','grafting_rate','article')


def test_doubles_group_delivery():
    p = maybe_plan('Quelle quantité a été livrée par client ou par ville ?', 'admin')
    assert p.dataset == 'historical_deliveries'
    assert p.group_by == 'client'
    assert p.extra_groups == ('city',)


def test_delivery_city_admin_routes_to_correct_source():
    p = maybe_plan('Combien de livraisons par ville ?', 'admin')
    assert (p.dataset,p.metric,p.group_by) == ('historical_deliveries','delivery_notes','city')


def test_delivery_default_historic_fallback_is_distinct_bons():
    p = maybe_plan('Combien de livraisons par client ?', 'admin')
    alternative = alternative_for_empty(p, 'Combien de livraisons par client ?', ADMIN)
    assert alternative is not None
    assert (alternative.dataset,alternative.metric,alternative.group_by) == (
        'historical_deliveries','delivery_notes','client')


def test_sown_species_fallback():
    p = maybe_plan('Combien de plants ont été semés par espèce ?', 'admin')
    assert p.dataset == 'operational_lots' and p.metric == 'sown'
    alternative = alternative_for_empty(p, 'Combien de plants ont été semés par espèce ?', ADMIN)
    assert (alternative.dataset,alternative.metric,alternative.group_by) == (
        'historical_production','sown','species')


def test_fallback_not_available_to_nonadmin():
    p = maybe_plan('Combien de plants ont été semés par espèce ?', 'production')
    assert alternative_for_empty(p,'Combien de plants ont été semés par espèce ?',PROD) is None


def test_explicit_current_does_not_fallback():
    p = maybe_plan('Combien de livraisons opérationnelles par client ?', 'admin')
    assert alternative_for_empty(p,'Combien de livraisons opérationnelles par client ?',ADMIN) is None


def test_no_invented_order_fallback():
    p = maybe_plan('Quelles commandes restent à livrer ?', 'admin')
    assert p.dataset == 'operational_preparations'
    assert alternative_for_empty(p, 'Quelles commandes restent à livrer ?', ADMIN) is None


def test_related_loss_rate_is_labeled_different():
    p = maybe_plan('Quels lots ont un ratio de perte supérieur à 30 % ?', 'admin')
    alt = alternative_for_empty(p,'Quels lots ont un ratio de perte supérieur à 30 % ?',ADMIN)
    assert alt is not None
    assert alt.dataset == 'historical_grafting' and alt.metric == 'total_loss_rate'
    assert 'DIFFÉRENTE' in fallback_notice(p,alt)


def test_procedure_is_not_routed_to_analytics():
    assert maybe_plan('Comment fonctionne le contrôle qualité avant livraison ?', 'admin') is None


def test_document_index_visible_and_procedure_retrievable(monkeypatch):
    monkeypatch.setenv('RAG_USE_EMBEDDINGS','0')
    root = HERE/'rag_documents'
    report = document_status(ADMIN,root)
    assert report['ready'] and report['visible_documents'] >= 2
    hits,_ = search_documents('Comment fonctionne le contrôle qualité avant livraison ?',ADMIN,root=root)
    assert hits and any('qualité' in item.title for item,_ in hits)


def test_llm_proposed_unknown_dataset_rejected():
    assert validate_plan({'dataset':'users','metric':'records','filters':{}},ADMIN) is None


def test_llm_proposed_historical_without_admin_rejected():
    assert validate_plan({'dataset':'historical_deliveries','metric':'records','filters':{}},PROD) is None
    assert 'historical_deliveries' not in allowed_catalog_summary(PROD)


def test_llm_proposed_operator_object_rejected():
    assert validate_plan({'dataset':'operational_lots','metric':'records','filters':{'site':{'$ne':'S1'}}},PROD) is None


def test_llm_proposed_safe_query_accepted():
    plan = validate_plan({'dataset':'operational_lots','metric':'sown','group_by':'species',
                         'filters':{'campaign':'C25'},'limit':10,'order':'desc'},PROD)
    assert plan and plan.metric == 'sown' and plan.filters['campaign'] == 'C25'


def test_presentation_short_table_no_internal_symbols():
    from test_rag_advanced_v3 import DB
    result = explore('operational_lots','sown','species',{},PROD,DB())
    nice = present_explore(result,'operational_lots','sown',{})
    assert nice['status']=='ok'
    assert nice['table']['rows']
    assert 'Regroupement : species' not in nice['answer']
    assert '0 groupe(s)' not in nice['answer']


def test_no_data_answer_is_honest():
    from test_rag_advanced_v3 import DB
    db = DB()
    db.deliveries.docs = []
    r = present_explore(explore('operational_deliveries','records','client',{},
                                {'role':'logistique','siteCodes':['S1']}, db),
                        'operational_deliveries','records',{})
    assert r['status']=='no_data'
    assert 'Aucune donnée exploitable' in r['answer']


def test_historical_delivery_distinct_bl_vs_excel_rows(monkeypatch):
    from rag import explorer
    from test_rag_advanced_v3 import DB
    rows=[{'_id':'d1','source_row':1,'delivery_note_number':'BL22','client':'Atlas','lot_code':'12345'},
          {'_id':'d2','source_row':2,'delivery_note_number':'BL22','client':'Atlas','lot_code':'12346'},
          {'_id':'d3','source_row':3,'delivery_note_number':'BL23','client':'Atlas','lot_code':'12347'}]
    monkeypatch.setattr(explorer,'_historical_records',lambda spec: iter(rows))
    r=explore('historical_deliveries','delivery_notes','client',{},ADMIN,DB())
    assert r['data_rows'][0]['value']==2
    assert r['data_rows'][0]['rows']==3


def test_partial_scan_not_misrepresented(monkeypatch):
    from rag import explorer
    from test_rag_advanced_v3 import DB
    monkeypatch.setattr(explorer,'MAX_MONGO_SCAN',1)
    result=explore('operational_lots','sown','species',{},PROD,DB())
    nice=present_explore(result,'operational_lots','sown',{})
    assert nice['provenance']['complete'] is False
    assert nice['warnings']


def test_llm_malformed_unhashable_plan_rejected():
    assert validate_plan({'dataset': ['production_lots'], 'metric':'records'},ADMIN) is None
    assert validate_plan({'dataset':'operational_lots', 'metric':['records']},ADMIN) is None


def test_pending_quality_does_not_confuse_already_blocked_lots():
    from test_rag_advanced_v3 import DB
    db=DB()
    db.production_lots.docs[0]['qualityStatus']='BLOQUE'
    db.production_lots.docs[1]['qualityStatus']='NON_CONTROLE'
    plan=maybe_plan('Combien de lots attendent encore un contrôle qualité ?', 'production')
    assert plan.filters['quality_status']=='__PENDING_QUALITY__'
    answer=explore(plan.dataset, plan.metric, plan.group_by, plan.filters, PROD,db)
    assert answer['meta']['matching_records']==1
