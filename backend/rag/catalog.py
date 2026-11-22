"""Audited read-only data dictionary for the SmartTrace analytical RAG.

Only the fields listed here may be used in a query. The LLM never constructs
MongoDB pipelines or chooses database fields outside this catalog.
"""
from __future__ import annotations
from dataclasses import dataclass

ALL_ROLES = ('admin', 'production', 'qualite', 'logistique', 'lecture')
LOGISTICS_ROLES = ('admin', 'logistique')


@dataclass(frozen=True)
class Metric:
    label: str
    kind: str                   # count, distinct, sum, avg, weighted_rate, computed_sum
    field: str = ''
    denominator: str = ''
    description: str = ''


@dataclass(frozen=True)
class Dataset:
    label: str
    source: str                 # MongoDB collection name OR historical type
    historical: bool
    roles: tuple[str, ...]
    dimensions: dict[str, str]  # public dimension -> source field
    metrics: dict[str, Metric]
    description: str
    date_field: str = ''


COMMON_HIST = {
    'lot_code': 'lot_code', 'campaign': 'campaign', 'species': 'species',
    'article': 'article', 'variety': 'variety',
}

CATALOG: dict[str, Dataset] = {
    'operational_lots': Dataset(
        'Lots opérationnels', 'production_lots', False, ALL_ROLES,
        {'lot_code':'code','campaign':'campaign','species':'species', 'article':'article',
         'variety':'variety','site':'siteCode','status':'status',
         'quality_status':'qualityStatus','lot_type':'lotType', 'month':'sownOn'},
        {'records':Metric('Nombre de fiches lot','count'),
         'lots':Metric('Nombre de lots distincts','distinct','_id'),
         'sown':Metric('Graines semées','sum','quantitySown'),
         'stock':Metric('Plants en stock','sum','plantsInStock'),
         'lost':Metric('Plants perdus','sum','plantsLost'),
         'delivered':Metric('Plants livrés','sum','plantsDelivered'),
         'reserved':Metric('Plants réservés','sum','plantsReserved'),
         'loss_rate':Metric('Ratio pertes / quantité semée (%)','weighted_rate','plantsLost','quantitySown',
                             'Ratio calculé uniquement sur les lots avec quantité semée > 0.')},
        'État courant des lots MongoDB. Les valeurs ne sont pas des mesures historiques Excel.',
        'sownOn'),
    'operational_germination': Dataset(
        'Germination opérationnelle', 'operational_germination', False, ALL_ROLES,
        {'lot_code':'code','site':'siteCode','campaign':'campaign',
         'species':'species','variety':'variety','article':'article','month':'occurredAt'},
        {'records':Metric('Nombre d’événements de germination valides','count'),
         'lots':Metric('Lots avec germination distincts','distinct','lotId'),
         'sown':Metric('Semences (événements GERMINATION)','sum','quantitySown'),
         'germinated':Metric('Plantules germées (événements)','sum','quantityGerminated'),
         'germination_rate':Metric('Taux réel enregistré germées/semées (%)','weighted_rate',
                                   'quantityGerminated','quantitySown',
                                   'Calculé depuis quantite_germee et quantite_semee des événements validés.')},
        'Événements réels de germination reliés à des lots accessibles, pas estimation Excel.',
        'occurredAt'),
    'operational_preparations': Dataset(
        'Préparations et commandes', 'preparations', False, LOGISTICS_ROLES,
        {'lot_code':'lotCodeReadable','site':'siteCode','client':'client','order':'orderReference',
         'location':'location','month':'createdAt'},
        {'records':Metric('Nombre de préparations','count'),
         'reserved':Metric('Quantité réservée (plants)','sum','quantityReserved'),
         'delivered':Metric('Quantité préparée déjà livrée (plants)','sum','quantityDelivered'),
         'pending':Metric('Quantité restant à livrer (plants)','computed_sum','pending')},
        'Réservations des commandes MongoDB; pending = max(0, reserved - delivered).', 'createdAt'),
    'operational_deliveries': Dataset(
        'Livraisons opérationnelles', 'deliveries', False, LOGISTICS_ROLES,
        {'lot_code':'lotCodeReadable','site':'siteCode','client':'client','delivery_note':'deliveryNote',
         'month':'date'},
        {'records':Metric('Nombre de livraisons','count'),
         'quantity':Metric('Quantité livrée (plants)','sum','quantity')},
        'Livraisons enregistrées dans les opérations MongoDB; distinctes des lignes Excel.', 'date'),
    'operational_events': Dataset(
        'Événements de traçabilité', 'trace_events', False, ALL_ROLES,
        {'site':'siteCode','event_type':'eventType','subject_type':'subjectType',
         'month':'occurredAt'},
        {'records':Metric('Nombre d’événements','count'),
         'events':Metric('Événements distincts','distinct','_id')},
        'Événements de l’audit opérationnel. Aucune certification Fabric implicite.', 'occurredAt'),
    'historical_production': Dataset(
        'Production historique Excel', 'production', True, ('admin',),
        {**COMMON_HIST,'depot':'production_site_or_depot','month':'sowing_date'},
        {'records':Metric('Nombre de lignes de production','count'),
         'lots':Metric('Codes de lot distincts','distinct','lot_code'),
         'sown':Metric('QteSemis_Rapport (semences)','sum','seeds_sown'),
         'plants_net':Metric('Net_Plants','sum','plants_net'),
         'plants_delivered':Metric('Livree_Plants (récapitulatif)','sum','plants_delivered_summary'),
         'germination_rate':Metric('Taux_Germination déclaré (%)','weighted_rate','germination_rate_pct','seeds_sown',
                 'Moyenne pondérée par QteSemis_Rapport, sur taux Excel déclarés; non certifiée.')},
        'Lignes historiques; jointure éventuelle par code à 5 chiffres seulement.', 'sowing_date'),
    'historical_grafting': Dataset(
        'Production greffée historique Excel', 'grafting', True, ('admin',),
        {**COMMON_HIST,'greenhouse':'greenhouse','grafting_type':'grafting_type',
         'month':'validated_on'},
        {'records':Metric('Nombre de lignes de greffage','count'),
         'lots':Metric('Codes de lot distincts','distinct','lot_code'),
         'plants_net':Metric('Net_Plants greffés','sum','plants_net'),
         'plants_destroyed':Metric('Plantes détruites déclarées','sum','plants_destroyed'),
         'grafting_rate':Metric('Taux_Greffage moyen déclaré (%)','avg','grafting_rate_pct'),
         'total_loss_rate':Metric('Perte_Totale moyenne déclarée (%)','avg','total_loss_pct'),
         'grafting_loss_rate':Metric('Perte_Greffage moyenne déclarée (%)','avg','grafting_loss_pct')},
        'Moyennes des lignes Excel (non pondérées), non certifiées et distinctes du stock MongoDB.',
        'validated_on'),
    'historical_deliveries': Dataset(
        'Livraisons historiques Excel', 'delivery', True, ('admin',),
        {**COMMON_HIST,'client':'client','city':'destination_city','governorate':'destination_governorate',
         'unit':'unit','type':'type','delivery_note':'delivery_note_number','depot':'depot','month':'document_date'},
        {'records':Metric('Nombre de lignes de livraison','count'),
         'lots':Metric('Codes de lot distincts','distinct','lot_code'),
         'delivery_notes':Metric('Bons distincts','distinct','delivery_note_number'),
         'item_quantity':Metric('Quantité Qte (unités du fichier)','sum','item_quantity',
                                description='Ne jamais additionner des unités différentes.'),
         'tray_quantity':Metric('Qte Pltx (plateaux déclarés)','sum','tray_quantity')},
        'Transactions historiques (livraisons/retours selon le type); dates documentaires, non confirmation physique.',
        'document_date'),
}

FILTER_LABELS = {
    'campaign':'Campagne', 'species':'Espèce', 'article':'Article', 'variety':'Variété',
    'site':'Site', 'status':'État du lot', 'quality_status':'Statut qualité',
    'lot_type':'Type de lot','lot_code':'Référence de lot', 'client':'Client',
    'city':'Ville','governorate':'Gouvernorat','unit':'Unité','delivery_note':'Bon de livraison',
    'event_type':'Type d’événement','order':'Commande', 'depot':'Dépôt',
    'grafting_type':'Type de greffage', 'greenhouse':'Serre', 'subject_type':'Type de sujet',
    'type':'Type de document', 'month':'Mois (AAAA-MM)', 'location':'Emplacement',
}


def public_catalog(user: dict) -> dict:
    role = user.get('role')
    return {'datasets': [
        {'id': key, 'label': spec.label, 'source': 'excel_non_certifie' if spec.historical else 'mongodb',
         'description': spec.description,
         'dimensions': [{'id': k, 'label': FILTER_LABELS.get(k,k)} for k in spec.dimensions],
         'metrics': [{'id': k, 'label': v.label, 'description': v.description} for k,v in spec.metrics.items()]}
        for key,spec in CATALOG.items() if role in spec.roles],
        'read_only': True,
        'note': 'Seules les données autorisées et les combinaisons du catalogue peuvent être interrogées.'}
