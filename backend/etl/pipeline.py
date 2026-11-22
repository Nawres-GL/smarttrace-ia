"""Build an auditable, conservative link between production and delivery Excel files.

Important decisions:
* Read originals only; never overwrite either Excel file.
* Link only on the five-digit LOT token. Article differences are warnings,
  and multiple production references remain explicit candidate groups.
* Preserve individual delivery lines, including returns and partial deliveries.
* Historical imports are snapshots, NOT verified production events.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .xlsx_reader import headers, rows

FIVE_DIGIT = re.compile(r"(?<!\d)(\d{5})(?!\d)")
YEAR_SUFFIX = re.compile(r"/(\d{2})\s*$")
EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_string(value) -> str:
    return "" if value is None else str(value).strip()


def normalize(value) -> str:
    s = unicodedata.normalize("NFKD", clean_string(value))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def lot_five_digits(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    s = clean_string(value)
    if isinstance(value, (float, int)) and float(value).is_integer():
        s = str(int(value))
    match = FIVE_DIGIT.search(s)
    return match.group(1) if match else None


def year_from_production_lot(value) -> int | None:
    m = YEAR_SUFFIX.search(clean_string(value))
    return (2000 + int(m.group(1))) if m else None


def excel_datetime(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (float, int)) and 30000 <= value <= 90000:
        dt = EXCEL_EPOCH + timedelta(days=float(value))
        return dt.isoformat(timespec="seconds") if value % 1 else dt.date().isoformat()
    if isinstance(value, str):
        return value.strip() or None
    return None


def number_or_none(value) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        s = str(value).strip().replace("\u00a0", "").replace(" ", "")
        s = s.replace(",", ".")
        result = float(s)
        return int(result) if result.is_integer() else result
    except (TypeError, ValueError):
        return None


def make_production_record(raw: dict, source_hash: str) -> dict:
    fields = raw["fields"]
    ref = clean_string(fields.get("LOT"))
    lot_code = lot_five_digits(ref) or lot_five_digits(fields.get("Lot_Production"))
    row = raw["excel_row"]
    return {
        "_id": f"production:{source_hash[:16]}:{row}",
        "source_file_sha256": source_hash,
        "source_row": row,
        "source_kind": "historical_excel_production",
        "lot_ref": ref,
        "lot_code": lot_code,
        "production_year": year_from_production_lot(ref),
        "article": clean_string(fields.get("Article")),
        "article_key": normalize(fields.get("Article")),
        "species": clean_string(fields.get("Espèce")),
        "variety": clean_string(fields.get("Variete")),
        "seed_lot_ref": clean_string(fields.get("Lot_Semence")),
        "production_site_or_depot": clean_string(fields.get("Depot")),
        "sowing_date": excel_datetime(fields.get("Date semis")),
        "germination_date_out": excel_datetime(fields.get("Date Sortie")),
        "seeds_sown": number_or_none(fields.get("QteSemis_Rapport")),
        "trays_net": number_or_none(fields.get("Qte Net Prod.")),
        "trays_delivered_summary": number_or_none(fields.get("Qte Livrée")),
        "plants_net": number_or_none(fields.get("Net_Plants")),
        "plants_delivered_summary": number_or_none(fields.get("Livree_Plants")),
        "tray_capacity": number_or_none(fields.get("Tray_Capacity")),
        "raw_cells": [{"column": key, "value": value} for key, value in fields.items()],
    }


def make_delivery_record(raw: dict, source_hash: str) -> dict:
    f = raw["fields"]
    row = raw["excel_row"]
    return {
        "_id": f"delivery:{source_hash[:16]}:{row}",
        "source_file_sha256": source_hash,
        "source_row": row,
        "source_kind": "historical_excel_delivery",
        "lot_ref_delivery": clean_string(f.get("N° Lot")),
        "lot_code": lot_five_digits(f.get("N° Lot")),
        "article": clean_string(f.get("Article")),
        "article_key": normalize(f.get("Article")),
        "species": clean_string(f.get("Espèce")),
        "type": clean_string(f.get("Type")),
        "client": clean_string(f.get("Client")),
        "delivery_note_number": clean_string(f.get("N° BOn")),
        "document_date": excel_datetime(f.get("Date Effet")),
        "unit": clean_string(f.get("Unité")),
        "tray_quantity": number_or_none(f.get("Qte Pltx")),
        "item_quantity": number_or_none(f.get("Qte")),
        "transporter": clean_string(f.get("Transporteur")),
        "depot": clean_string(f.get("Depot")),
        "destination_city": clean_string(f.get("Ville Client")),
        "destination_governorate": clean_string(f.get("Gouvernorat")),
        "campaign": clean_string(f.get("Compagne")),
        "raw_cells": [{"column": key, "value": value} for key, value in f.items()],
    }




def make_graft_record(raw: dict, source_hash: str) -> dict:
    '''Read-only projection for grafted-production workbook. NEVER infer a grafting event/date.'''
    fields = raw['fields']
    code = lot_five_digits(fields.get('Lot_Production')) or lot_five_digits(fields.get('LOT'))
    return {
        '_id': f'graft:{source_hash[:16]}:{raw["excel_row"]}',
        'source_file_sha256': source_hash, 'source_row': raw['excel_row'],
        'source_kind': 'historical_excel_grafted_production',
        'lot_ref': clean_string(fields.get('LOT')), 'lot_code': code,
        'lot_production': clean_string(fields.get('Lot_Production')),
        'article': clean_string(fields.get('Article')),
        'species': clean_string(fields.get('Espèce')),
        'variety': clean_string(fields.get('Variete')),
        'greenhouse': clean_string(fields.get('Serre')),
        'grafting_type': clean_string(fields.get('Motif')),
        'seed_lot_ref': clean_string(fields.get('Lot_Semence')),
        'ds_reel_source': excel_datetime(fields.get('DS. Réel')),
        'validated_on': excel_datetime(fields.get('Validé Le')),
        'grafting_rate_pct': number_or_none(fields.get('Taux_Greffage')),
        'grafting_loss_pct': number_or_none(fields.get('Perte_Greffage')),
        'total_loss_pct': number_or_none(fields.get('Perte_Totale')),
        'grafted_trays_gross': number_or_none(fields.get('Brut')),
        'grafted_trays_net': number_or_none(fields.get('Qte Net')),
        'plants_gross': number_or_none(fields.get('Brut_Plants')),
        'plants_net': number_or_none(fields.get('Net_Plants')),
        'plants_delivered': number_or_none(fields.get('Livree_Plants')),
        'plants_destroyed': number_or_none(fields.get('Destruction_Plants')),
        'tray_capacity': number_or_none(fields.get('Tray_Capacity')),
        'status_validated': clean_string(fields.get('Validé')),
    }

def build_matches(productions: list[dict], deliveries: list[dict]) -> list[dict]:
    """Connect rows by the FIVE DIGIT LOT ONLY; no article/date/quantity join filters.

    Multiple original production refs remain explicit candidates: never invent one.
    """
    by_code: dict[str, list[dict]] = defaultdict(list)
    for p in productions:
        if p["lot_code"]:
            by_code[p["lot_code"]].append(p)
    links = []
    for d in deliveries:
        code = d["lot_code"]
        candidates = by_code.get(code, []) if code else []
        refs = sorted({p["lot_ref"] for p in candidates if p["lot_ref"]})
        article_disagreement = bool(candidates and d["article_key"] and
                                     all(p["article_key"] != d["article_key"] for p in candidates))
        status = ("NO_5_DIGIT_LOT" if not code else
                  "NO_PRODUCTION_LOT" if not candidates else
                  "MULTIPLE_LOT_REFERENCES" if len(refs) > 1 else "LINKED_BY_LOT")
        links.append({
            "_id": f"link:{d['_id']}",
            "delivery_record_id": d["_id"],
            "delivery_source_row": d["source_row"],
            "delivery_lot_reference": d["lot_ref_delivery"],
            "lot_code": code,
            "delivery_article": d["article"],
            "matching_status": status,
            "matched_production_lot_ref": refs[0] if len(refs) == 1 else None,
            "matched_article": None,
            "production_source_ids": [p["_id"] for p in candidates],
            "candidate_lot_refs": refs,
            "article_difference_warning": article_disagreement,
            "campaign_year_warning": False,
        })
    return links


def analyze(production_path: Path, delivery_path: Path) -> tuple[dict, list[dict], list[dict], list[dict]]:
    p_hash = digest_file(production_path)
    d_hash = digest_file(delivery_path)
    p_headers, d_headers = headers(production_path), headers(delivery_path)
    required_p = ["LOT", "Article", "Qte Livrée", "Lot_Semence"]
    required_d = ["N° Lot", "Article", "Type", "Client", "N° BOn", "Qte", "Date Effet"]
    for kind, actual, needed in (("Production", p_headers, required_p), ("Delivery", d_headers, required_d)):
        missing = [h for h in needed if h not in actual]
        if missing:
            raise ValueError(f"{kind}: missing required columns: {', '.join(missing)}")
    prod = [make_production_record(r, p_hash) for r in rows(production_path)]
    delivery = [make_delivery_record(r, d_hash) for r in rows(delivery_path)]
    links = build_matches(prod, delivery)
    status = Counter(x["matching_status"] for x in links)
    tcounts = Counter(d["type"] for d in delivery)
    report = {
        "sources": {"production": {"file": production_path.name, "sha256": p_hash, "columns": len(p_headers)},
                    "delivery": {"file": delivery_path.name, "sha256": d_hash, "columns": len(d_headers)}},
        "counts": {
            "production_rows": len(prod),
            "delivery_rows": len(delivery),
            "production_distinct_lot_refs": len({p["lot_ref"] for p in prod if p["lot_ref"]}),
            "distinct_5_digit_lot_codes_production": len({p["lot_code"] for p in prod if p["lot_code"]}),
            "status_by_delivery_line": dict(status),
            "delivery_line_types": dict(tcounts),
            "year_warnings_in_matched_lines": sum(x["campaign_year_warning"] for x in links),
            "matched_distinct_lot_refs": len({x["matched_production_lot_ref"] for x in links if x["matched_production_lot_ref"]}),
        },
        "rules": [
            "Only a five-digit lot token is used for candidate lookup.",
            "Matching uses ONLY normalized five-digit lot codes; article is informational.",
            "Multiple production references remain candidates and are never silently merged.",
            "Document date is not assumed to be the physical delivery confirmation date.",
            "Delivery and returns remain separate original transaction lines.",
            "No historical Excel row is presented as a Blockchain-certified event.",
            "No unit conversion or quantity reconciliation is inferred from a lot-only match.",
        ],
    }
    return report, prod, delivery, links


def write_preview(output: Path, report: dict, productions: list[dict], deliveries: list[dict], links: list[dict]):
    output.mkdir(parents=True, exist_ok=True)
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    delivery_by_id = {d["_id"]: d for d in deliveries}
    with (output/"delivery_match_review.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        cols = ["delivery_row", "delivery_lot", "lot_5_digits", "delivery_article", "type", "date_effet", "bon_livraison", "qte_pltx", "qte", "unit", "status", "production_lot", "candidate_refs", "year_warning"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for link in links:
            d = delivery_by_id[link["delivery_record_id"]]
            w.writerow({
                "delivery_row": d["source_row"], "delivery_lot": d["lot_ref_delivery"],
                "lot_5_digits": link["lot_code"], "delivery_article": d["article"],
                "type": d["type"], "date_effet": d["document_date"],
                "bon_livraison": d["delivery_note_number"], "qte_pltx": d["tray_quantity"],
                "qte": d["item_quantity"], "unit": d["unit"],
                "status": link["matching_status"],
                "production_lot": link["matched_production_lot_ref"],
                "candidate_refs": " | ".join(link["candidate_lot_refs"]),
                "year_warning": link["campaign_year_warning"],
            })
    # Full production originals stay in Excel and, if approved, in the Atlas historical collection.
    # This small preview helps check matching keys without duplicating sensitive raw records.
    with (output/"production_lot_index.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        cols = ["production_row", "full_lot", "lot_5_digits", "article", "species", "seed_lot", "net_plants", "delivered_plants_summary"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in productions:
            w.writerow({"production_row":p["source_row"], "full_lot":p["lot_ref"], "lot_5_digits":p["lot_code"],
                        "article":p["article"], "species":p["species"], "seed_lot":p["seed_lot_ref"],
                        "net_plants":p["plants_net"], "delivered_plants_summary":p["plants_delivered_summary"]})
