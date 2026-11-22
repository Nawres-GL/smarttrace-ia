"""Conservative, testable detection of *possible* edits in uploaded Excel.

A repeated business key is not necessarily the same physical row. Only uniquely
matched keys are quarantined for human review; nothing is auto-overwritten.
"""
from collections import Counter, defaultdict
from etl.incremental import fingerprint_record

ALT_KEYS = {
    'production': ('lot_ref','sowing_date'),
    'livraison': ('delivery_note_number','lot_code','document_date'),
    'greffage': ('lot_production','greenhouse','ds_reel_source'),
}
KEYS = {
    'production': ('lot_ref', 'sowing_date', 'article_key'),
    'livraison': ('delivery_note_number', 'lot_code', 'article_key', 'document_date', 'client'),
    'greffage': ('lot_production', 'greenhouse', 'variety', 'ds_reel_source'),
}
# Immutable identity fields cannot be rewritten through review.
EDITABLE = {
    'production': ('seeds_sown','trays_net','plants_net','trays_delivered_summary',
                   'plants_delivered_summary','germination_date_out','tray_capacity'),
    'livraison': ('item_quantity','tray_quantity','destination_city','destination_governorate',
                  'transporter','unit','depot'),
    'greffage': ('grafting_rate_pct','grafting_loss_pct','total_loss_pct',
                 'grafted_trays_gross','grafted_trays_net','plants_gross','plants_net',
                 'plants_delivered','plants_destroyed','tray_capacity','validated_on'),
}

def business_key(kind, row, fallback=False):
    names=ALT_KEYS[kind] if fallback else KEYS[kind]
    parts = tuple(str(row.get(field) or '').strip().casefold() for field in names)
    return parts if all(parts) else None

def split_possible_corrections(kind, additions, existing_rows):
    """Return (safe additions, review candidates), deterministic and conservative.

    Identity key must be nonempty and unique on BOTH sides. A different row
    fingerprint plus editable-field differences is a suspect, not a correction.
    Multiple occurrences are *never* auto-matched.
    """
    old_by_key = defaultdict(list)
    old_by_fallback=defaultdict(list)
    for item in existing_rows:
        key=business_key(kind,item)
        fallback=business_key(kind,item,True)
        if key: old_by_key[key].append(item)
        if fallback: old_by_fallback[fallback].append(item)
    new_keys=Counter(business_key(kind,item) for item in additions)
    new_fallbacks=Counter(business_key(kind,item,True) for item in additions)
    safe, reviews = [], []
    for item in additions:
        key=business_key(kind,item)
        fallback=business_key(kind,item,True)
        old = old_by_key.get(key,[]) if key else []
        identity_changed=False
        if not old and fallback:
            old=old_by_fallback.get(fallback,[])
            identity_changed=bool(old)
        if not old:
            safe.append(item)
            continue
        original=old[0]
        ambiguous = (identity_changed or len(old)!=1 or new_keys[key]!=1 or
                     (fallback is not None and new_fallbacks[fallback]!=1))
        differences={name: {'before':original.get(name),'after':item.get(name)}
                     for name in EDITABLE[kind] if original.get(name)!=item.get(name)}
        if not ambiguous and fingerprint_record(item)==fingerprint_record(original):
            safe.append(item)
            continue
        reviews.append({'kind':kind,'original_id':original['_id'],
                        'source_row':item.get('source_row'), 'lot_code':item.get('lot_code'),
                        'new_record':item,'differences':differences,
                        'candidate_key':list(key or fallback or ()), 'ambiguous':ambiguous,
                        'reason':('Identité ou clé ambiguë : ne pas fusionner automatiquement.' if ambiguous
                                  else 'Même clé métier unique, mais valeurs différentes : confirmation humaine requise.')})
    return safe, reviews
