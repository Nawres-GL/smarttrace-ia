"""Testable, database-independent exact row deduplication with multiplicity."""
import hashlib
import json
from collections import Counter

def _canonical(value):
    if value is None or value == '':
        return ''
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.strip()
    return value


def row_fingerprint(raw_cells) -> str:
    """Canonical content hash ignoring order of columns and file row numbers.

    Two genuinely identical rows can be legitimate separate lines, so the algorithm
    tracks their multiplicity (see preview_plan), not just a set of hashes.
    """
    if isinstance(raw_cells, dict):
        data = raw_cells
    else:
        data = {item['column']: item.get('value') for item in raw_cells}
    canonical = {str(k).strip(): _canonical(v) for k, v in data.items() if str(k).strip()}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def fingerprint_record(rec):
    # Earlier graft imports did not preserve raw_cells; use their stable projected
    # fields for BOTH legacy and newly uploaded graft rows.
    if rec.get('source_kind') == 'historical_excel_grafted_production':
        excluded = {'_id','source_row','source_file_sha256','source_kind',
                    'raw_cells','contentFingerprint','contentOccurrence'}
        return row_fingerprint({key:value for key,value in rec.items() if key not in excluded})
    return row_fingerprint(rec.get('raw_cells', []))


def preview_plan(records, existing):
    occurrences = Counter()
    additions = []
    duplicates = 0
    for rec in records:
        fp = fingerprint_record(rec)
        occurrences[fp] += 1
        if occurrences[fp] <= existing[fp]:
            duplicates += 1
        else:
            entry = dict(rec)
            entry['contentFingerprint'] = fp
            entry['_id'] = 'v2:' + rec['source_kind'].replace('historical_excel_', '') + ':' + fp[:32] + ':' + str(occurrences[fp])
            entry['contentOccurrence'] = occurrences[fp]
            additions.append(entry)
    return {'total': len(records), 'duplicates': duplicates, 'new': len(additions)}, additions

