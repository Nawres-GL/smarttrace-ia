"""Usage (from backend directory):

python -m etl.cli analyze --production ... --delivery ...
python -m etl.cli import --production ... --delivery ... --confirm-import

Dry-run `analyze` never writes to Atlas. Import writes HISTORICAL collections
only. It does not fabricate validated event logs or Blockchain proofs.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import analyze, write_preview, make_graft_record, digest_file
from .xlsx_reader import rows


def main():
    parser = argparse.ArgumentParser(description="Royal Plants SmartTrace — historical Excel ETL")
    parser.add_argument("mode", choices=["analyze", "import"])
    parser.add_argument("--production", required=True, type=Path)
    parser.add_argument("--delivery", required=True, type=Path)
    parser.add_argument("--grafting", type=Path, help="Optional original grafted-production workbook")
    parser.add_argument("--out", type=Path, default=Path("etl_output"))
    parser.add_argument("--confirm-import", action="store_true")
    args = parser.parse_args()
    for source in (args.production, args.delivery):
        if not source.is_file():
            parser.error(f"File not found: {source}")
    if args.grafting and not args.grafting.is_file():
        parser.error(f"Grafting file not found: {args.grafting}")
    report, productions, deliveries, links = analyze(args.production, args.delivery)
    graft_hash = digest_file(args.grafting) if args.grafting else None
    grafts = [make_graft_record(r, graft_hash) for r in rows(args.grafting)] if graft_hash else []
    report['counts']['grafting_rows'] = len(grafts)
    if args.grafting:
        report['sources']['grafting'] = {'file':args.grafting.name,'sha256':graft_hash}
    write_preview(args.out, report, productions, deliveries, links)
    print(json.dumps(report["counts"], indent=2, ensure_ascii=False))
    print("Preview created:", args.out.resolve())
    if args.mode == "analyze":
        print("DRY RUN: No MongoDB documents were created or changed.")
        return
    if not args.confirm_import:
        parser.error("Import requires --confirm-import; review etl_output first.")
    try:
        from dotenv import load_dotenv
        from pymongo import MongoClient, ReplaceOne
    except ImportError as ex:
        parser.error(f"Missing backend dependencies: {ex}. Install requirements.txt")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    mongo_uri = os.getenv("MONGODB_URI", "")
    database_name = os.getenv("MONGODB_DB", "")
    if not mongo_uri or not database_name:
        parser.error("Set MONGODB_URI and MONGODB_DB in backend/.env")
    if os.getenv("APP_ENV", "development").lower() not in {"development", "dev"}:
        parser.error("Safety guard: historical ETL import is allowed only in APP_ENV=development")
    with MongoClient(mongo_uri, serverSelectionTimeoutMS=10000) as client:
        client.admin.command("ping")
        database = client[database_name]
        # ReplaceOne upserts are idempotent for the same source file checksum + Excel row.
        for collection_name, docs in [
            ("historical_production_records", productions),
            ("historical_delivery_lines", deliveries),
            ("historical_delivery_links", links),
            ("historical_grafting_records", grafts),
        ]:
            collection = database[collection_name]
            for pos in range(0, len(docs), 300):
                batch = docs[pos:pos + 300]
                collection.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in batch], ordered=False)
            print(f"{collection_name}: {len(docs)} source records upserted")
        database["historical_import_batches"].replace_one(
            {"_id": "batch:" + report["sources"]["production"]["sha256"][:16] + ":" + report["sources"]["delivery"]["sha256"][:16]},
            {"_id": "batch:" + report["sources"]["production"]["sha256"][:16] + ":" + report["sources"]["delivery"]["sha256"][:16],
             "created_or_verified_at": datetime.now(timezone.utc), "report": report}, upsert=True)
        for c, keys in [("historical_production_records", [("lot_code", 1), ("article_key", 1)]),
                        ("historical_delivery_lines", [("lot_code", 1), ("article_key", 1)]),
                        ("historical_delivery_links", [("matched_production_lot_ref", 1)]),
                        ("historical_grafting_records", [("lot_code",1)])]:
            database[c].create_index(keys)
    print("Import finished. Historical collections ONLY; no live events or Fabric transactions created.")


if __name__ == "__main__":
    main()
