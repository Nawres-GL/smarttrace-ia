"""One-time bootstrap. Dry-run default; --commit writes to existing Atlas DB.

Usage: python -m scripts.bootstrap_history_atlas --production ... --livraison ... --greffage ...
       python -m scripts.bootstrap_history_atlas --production ... --livraison ... --greffage ... --commit
"""
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient, InsertOne
from pymongo.errors import BulkWriteError
from app.historical_imports import SOURCES, _parse_file, existing_fingerprints, _validate_schema
from app.unified_registry import sync_historical_registry, sync_operational_registry
from etl.incremental import preview_plan


def run(args):
    load_dotenv(Path(__file__).resolve().parents[1]/'.env')
    if not os.getenv('MONGODB_URI'):
        raise SystemExit('MONGODB_URI absent du backend/.env local.')
    client=MongoClient(os.environ['MONGODB_URI'],serverSelectionTimeoutMS=15000)
    db=client[os.getenv('MONGODB_DB','royal_plants_smarttrace_dev')]
    client.admin.command('ping')
    plans=[]
    for kind,filename in [('production',args.production),('livraison',args.livraison),('greffage',args.greffage)]:
        path=Path(filename)
        if not path.is_file():raise SystemExit('Fichier introuvable: '+str(path))
        collection_name, schema, file_hash, records = _parse_file(path,kind)
        _validate_schema(db,kind,schema)
        counts, additions=preview_plan(records,existing_fingerprints(db[collection_name]))
        plans.append((kind,collection_name,schema,additions,counts))
        print(kind.upper(), '| reçues:',counts['total'],'| déjà présentes:',counts['duplicates'],'| nouvelles:',counts['new'])
    if not args.commit:
        print('PRÉVISUALISATION UNIQUEMENT. Ajoutez --commit pour insérer les nouvelles lignes.')
        return
    for kind,name,schema,additions,counts in plans:
        added=0
        for start in range(0,len(additions),250):
            try:
                result=db[name].bulk_write([InsertOne(r) for r in additions[start:start+250]],ordered=False)
                added+=result.inserted_count
            except BulkWriteError as ex:
                if any(e.get('code')!=11000 for e in ex.details.get('writeErrors',[])):
                    raise
                added+=ex.details.get('nInserted',0)
        from datetime import datetime,timezone
        db.historical_import_schemas.update_one({'_id':kind},{'$setOnInsert':{
            'columns':schema,'createdAt':datetime.now(timezone.utc)}},upsert=True)
        print(kind,':',added,'ajoutée(s)')
    historical=sync_historical_registry(db)
    operational=sync_operational_registry(db)
    print('Registre synchronisé:',historical,'lots historiques,',operational,'lots opérationnels.')
    print('Après vérification des trois collections, placer HISTORY_MODE=atlas dans backend/.env et redémarrer FastAPI.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Import contrôlé des trois archives Excel dans MongoDB Atlas.')
    for label in ('production','livraison','greffage'):
        parser.add_argument('--'+label,required=True)
    parser.add_argument('--commit',action='store_true',help='Confirmer la migration après la prévisualisation')
    run(parser.parse_args())
