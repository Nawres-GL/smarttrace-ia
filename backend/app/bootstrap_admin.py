"""Run once after configuring backend/.env and MongoDB Atlas.

ADMIN_EMAIL and ADMIN_PASSWORD are environment variables; never hardcode passwords.
"""
import os
from uuid import uuid4
from dotenv import load_dotenv
from pymongo import MongoClient
from app.auth import passwords


def main():
    load_dotenv()
    uri = os.environ.get('MONGODB_URI')
    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    secret = os.environ.get('JWT_SECRET', '')
    if not uri or '@' not in email or len(password) < 12 or len(secret) < 32:
        raise SystemExit('Configure MONGODB_URI, ADMIN_EMAIL, ADMIN_PASSWORD (12+), JWT_SECRET (32+) in backend/.env')
    with MongoClient(uri, serverSelectionTimeoutMS=10000) as client:
        client.admin.command('ping')
        db = client[os.getenv('MONGODB_DB', 'royal_plants_smarttrace_dev')]
        db.users.create_index('email', unique=True)
        if db.users.find_one({'email': email}):
            print('Compte existant : aucun changement.')
            return
        db.users.insert_one({'_id': str(uuid4()), 'email': email, 'name': 'Administrateur pilote',
                             'passwordHash': passwords.hash(password), 'role': 'admin',
                             'siteCodes': ['S01'], 'disabled': False})
        print('Compte administrateur pilote créé. Retirez ADMIN_PASSWORD de .env après usage.')

if __name__ == '__main__':
    main()
