"""Explicit local-only admin password rotation. Never print secrets.

Usage: python -m app.admin_tools --reset-admin-password --confirm
Set ADMIN_EMAIL / ADMIN_PASSWORD in private .env first. Do not expose to public users.
"""
import argparse
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from app.auth import passwords


def main():
    parser = argparse.ArgumentParser(description='Pilot administrator maintenance')
    parser.add_argument('--reset-admin-password', action='store_true')
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    if not (args.reset_admin_password and args.confirm):
        parser.error('Use --reset-admin-password --confirm to explicitly authorize reset.')
    load_dotenv()
    if os.getenv('APP_ENV','development') != 'development':
        raise SystemExit('Command only allowed in development.')
    email = os.getenv('ADMIN_EMAIL','').strip().lower()
    password = os.getenv('ADMIN_PASSWORD','')
    uri = os.getenv('MONGODB_URI','')
    if '@' not in email or len(password)<12 or not uri:
        raise SystemExit('Configure ADMIN_EMAIL, ADMIN_PASSWORD (12+) and MONGODB_URI privately.')
    with MongoClient(uri,serverSelectionTimeoutMS=10000) as client:
        client.admin.command('ping')
        db = client[os.getenv('MONGODB_DB','royal_plants_smarttrace_dev')]
        result=db.users.update_one({'email':email,'role':'admin','disabled':{'$ne':True}},
                                   {'$set':{'passwordHash':passwords.hash(password)}})
        if result.matched_count == 0:
            raise SystemExit('Administrateur introuvable : executez bootstrap_admin si aucun compte n’existe.')
        print('Mot de passe administrateur mis à jour. Retirez ADMIN_PASSWORD de .env.')

if __name__=='__main__':main()
