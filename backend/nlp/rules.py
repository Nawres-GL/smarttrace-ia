"""Offline French domain parser — deterministic BASELINE, not a Transformer model.

Safe by construction: returns drafts; never writes to MongoDB or executes operations.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INTENTS = {
    'RECEPTION_SEMENCES': ('reception', 'recu des semences', 'receptionne', 'reception semences', 'arrivage semences'),
    'SEMIS': ('semis', 'seme', 'ensemence', 'mise en plateau'),
    'GERMINATION': ('germination', 'germe', 'levee', 'plants leves'),
    'TRANSFERT': ('transfert', 'transfere', 'transferer', 'deplace', 'deplacement', 'vers la serre', 'vers chambre'),
    'PERTES': ('pertes', 'perdu', 'perdus', 'perdue', 'perte', 'mortalite', 'detruit', 'destruction'),
    'INTERVENTION': ('traitement', 'traite', 'traiter', 'intervention', 'entretien', 'pulverisation', 'observation'),
    'GREFFAGE': ('greffage', 'greffe', 'greffer', 'greffons', 'porte greffe'),
    'CONTROLE_QUALITE': ('qualite', 'controle', 'inspection', 'conforme', 'homogene', 'etat sanitaire'),
    'PREPARATION': ('preparation', 'prepare', 'reserver', 'reserve', 'commande'),
    'LIVRAISON': ('livraison', 'livre', 'livrer', 'expedie', 'expedition', 'transporteur'),
    'RETOUR': ('retour', 'retourne', 'retour client', 'retourne par'),
}
# Substring match uses word boundaries to avoid detecting "seme" inside an unrelated word.
ACTION = {
    'RECEPTION_SEMENCES':'seed','SEMIS':'sowing','GERMINATION':'germination',
    'TRANSFERT':'transfer','PERTES':'loss','INTERVENTION':'treatment',
    'GREFFAGE':'graft','CONTROLE_QUALITE':'quality','PREPARATION':'preparation',
    'LIVRAISON':'delivery','RETOUR':'return',
}
REQUIRED = {
    'seed':('supplier','supplier_lot_number','species','variety','quantity_received','received_on'),
    'sowing':('seed_lot_id','quantity_sown','sown_on','tray_type','tray_count','tray_capacity','substrate'),
    'germination':('quantity','location','started_on','ended_on','observed_on','duration_hours'),
    'transfer':('quantity','origin','destination'),
    'loss':('quantity','location','reason'),
    'treatment':('name','intervention_type','location','performed_on'),
    'graft':('rootstock_lot_id','scion_location','rootstock_location','quantity_used','quantity_success','grafted_on'),
    'quality':('approved','inspected_quantity','approved_quantity','sanitary_status','homogeneity','inspected_on','notes'),
    'preparation':('client','order_reference','quantity','location'),
    'delivery':('preparation_id','quantity','delivery_note','transporter','vehicle','received_by','receipt_confirmed','delivered_on'),
    'return':('preparation_id','quantity','reason','returned_on'),
}


def ascii_lower(s: str) -> str:
    s = unicodedata.normalize('NFKD', s.casefold())
    return ''.join(ch for ch in s if not unicodedata.combining(ch))


def classify(text: str):
    plain = ascii_lower(text)
    scores = {}
    for key, phrases in INTENTS.items():
        hits = [p for p in phrases if re.search(r'(?<!\w)'+re.escape(p)+r'(?!\w)', plain)]
        if hits:
            scores[key] = max(len(p) for p in hits)
    if not scores:
        return None, ['Aucune opération reconnue.'], 0.0
    top = sorted(scores, key=lambda k:scores[k], reverse=True)
    # A text describing multiple operations must be split manually; don't execute the wrong one.
    if len(top) > 1:
        return None, ['Plusieurs opérations détectées : '+', '.join(top)+'. Saisissez une opération à la fois.'], 0.0
    # This is a *heuristic signal*, NOT a calibrated model probability.
    return top[0], [], 0.65


def _date(text: str, today=None):
    now = today or datetime.now(ZoneInfo('Africa/Tunis')).date()
    norm = ascii_lower(text)
    d = re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)', norm)
    if d:
        try:
            return datetime(int(d[3]), int(d[2]), int(d[1])).date().isoformat()
        except ValueError:
            return None
    if re.search(r'\bavant[- ]hier\b', norm):return (now-timedelta(days=2)).isoformat()
    if re.search(r'\bhier\b',norm):return (now-timedelta(days=1)).isoformat()
    if re.search(r"\baujourd['’ ]hui\b",norm):return now.isoformat()
    return None


def _locations(text):
    norm = ascii_lower(text)
    results=[]
    for m in re.finditer(r'\b(chambre|serre|tunnel|zone)[\s-]*(?:n[°o]\s*)?(\d{1,3})\b',norm):
        results.append({'start':m.start(),'end':m.end(),'value':f'{m[1].upper()}-{int(m[2]):02d}'})
    return results


def _lot(text):
    # Only capture identifiers next to an explicit 'lot' label (not quantities or dates).
    m = re.search(r'\b(?:lot|n[°o]\s*lot)\s*(?:de\s*)?(?:n[°o]\s*)?[:#-]?\s*((?:RO-\d{5}/\d{2}|GRO-G\d{5}/?|RP-[A-Z0-9-]{5,60}|\d{5}))\b',text,re.I)
    if m:return m[1].rstrip('/')
    # Alternative 'lot RO-12345/25' with punctuation ending at /.
    m = re.search(r'\blot\s+(RO-\d{5}/\d{2}|GRO-G\d{5}/?)',text,re.I)
    return m[1] if m else None


def _number_after(text, words):
    norm=ascii_lower(text)
    pat=r'\b(?:'+ '|'.join(re.escape(w) for w in words) +r')\s*[:=]?\s*(\d{1,7})\b'
    m=re.search(pat,norm)
    return int(m[1]) if m else None


def _qty(text):
    norm=ascii_lower(text)
    m=re.search(r'(?<!\d)(\d{1,3}(?:[ \u202f]\d{3})+|\d{1,7})(?:\s+)(?:plants?|graines?|semences?|greffes?)(?!\w)',norm)
    if m:return int(re.sub(r'\s','',m[1]))
    return _number_after(text, ('quantite','qte','nombre de plants'))


def _temperature(text):
    norm=ascii_lower(text)
    m=re.search(r'(?<!\w)(-?\d{1,2}(?:[.,]\d+)?)\s*(?:°\s*c|degres)',norm)
    return float(m[1].replace(',','.')) if m else None


def _humidity(text):
    norm=ascii_lower(text)
    m=re.search(r'(?<!\w)(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:d[’\']?humidite)?',norm)
    if not m:m=re.search(r'\bhumidite\s*[:=]?\s*(\d{1,3}(?:[.,]\d+)?)',norm)
    return float(m[1].replace(',','.')) if m else None


def extract(text: str, today=None):
    intent, warnings, signal = classify(text)
    fields={}
    if not intent:return {'intent':None,'action':None,'fields':{},'lot_reference':None,'missing':[], 'warnings':warnings,'confidence':0.0,'engine':'rules-v1'}
    action=ACTION[intent]
    norm=ascii_lower(text)
    qty=_qty(text)
    if qty is not None:
        if action=='seed':fields['quantity_received']=qty
        elif action=='sowing':fields['quantity_sown']=qty
        elif action=='graft':fields['quantity_used']=qty
        elif action=='quality':fields['inspected_quantity']=qty
        else:fields['quantity']=qty
    locations=_locations(text)
    if action=='transfer':
        if len(locations)>=2:
            fields['origin']=locations[0]['value'];fields['destination']=locations[1]['value']
        else:warnings.append('Origine et destination doivent être précisées.')
    elif locations:
        fields[('scion_location' if action=='graft' else 'location')]=locations[0]['value']
    d=_date(text,today)
    datefield={'seed':'received_on','sowing':'sown_on','germination':'observed_on',
               'treatment':'performed_on','graft':'grafted_on','quality':'inspected_on','delivery':'delivered_on','return':'returned_on'}.get(action)
    if d and datefield:fields[datefield]=d
    if action=='germination':
        t=_temperature(text);h=_humidity(text)
        if t is not None:fields['temperature']=t
        if h is not None:fields['humidity']=h
        dur=re.search(r'\b(?:duree\s*(?:de\s*)?)?(\d{1,4})\s*(?:h|heures?)\b',norm)
        if dur:fields['duration_hours']=int(dur[1])
    if action=='treatment':
        fields['intervention_type']='TRAITEMENT' if any(x in norm for x in ('traitement','traite','pulveris')) else 'OBSERVATION' if 'observation' in norm else 'ENTRETIEN'
        if 'traitement' in norm: fields['name']='Traitement signalé — à préciser'
    if action=='loss':
        # Do not invent a causal explanation from an unstructured report.
        warnings.append('Précisez et vérifiez le motif des pertes.')
    if action=='quality':
        if 'non conforme' in norm or 'non-conforme' in norm:
            fields['approved']=False;fields['sanitary_status']='NON_CONFORME'
        elif 'conforme' in norm:
            fields['approved']=True
        fields['homogeneity']='HETEROGENE' if 'heterogene' in norm else 'HOMOGENE' if 'homogene' in norm else 'A_VERIFIER'
    if action=='graft':
        s=_number_after(text,('reussies','reussis','greffes reussies'))
        if s is not None:fields['quantity_success']=s
    if action=='delivery':
        if any(x in norm for x in ('reception confirmee','client a confirme')):fields['receipt_confirmed']=True
    if action=='return':warnings.append('Sélectionnez la préparation et vérifiez la date de livraison précédente.')
    if 'ne pas' in norm or re.search(r'\bn[’\'](?:est|a|ont|avons|ai|pas)\b.*\bpas\b',norm):
        warnings.append('Une négation a été détectée : reformulez votre instruction avant de continuer.')
    missing=[name for name in REQUIRED[action] if name not in fields]
    return {'intent':intent,'action':action,'fields':fields,'lot_reference':_lot(text),
            'missing':missing,'warnings':warnings,'confidence':signal,
            'engine':'rules-v1'}
