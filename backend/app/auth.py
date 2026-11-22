"""Pilot JWT authentication. Use HTTPS and rotate secrets for deployment.

Access is deny-by-default: business routes require a verified user.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from secrets import token_urlsafe
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix='/api/auth', tags=['Accès sécurisé'])
security = HTTPBearer(auto_error=False)
passwords = PasswordHasher()
ROLES = {'admin', 'production', 'qualite', 'logistique', 'lecture'}


def database(request: Request):
    db = request.app.state.db
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas non configuré.')
    return db


def secret():
    value = os.getenv('JWT_SECRET', '')
    if len(value) < 32:
        raise HTTPException(503, 'JWT_SECRET doit contenir au moins 32 caractères.')
    return value


def authenticated_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]):
    if credentials is None:
        raise HTTPException(401, 'Authentification requise.', headers={'WWW-Authenticate': 'Bearer'})
    try:
        claims = jwt.decode(credentials.credentials, secret(), algorithms=['HS256'], options={'require': ['exp', 'sub']})
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, 'Session expirée ou invalide.')
    user = database(request).users.find_one({'_id': claims['sub'], 'disabled': {'$ne': True}})
    if user is None or claims.get('v', 0) != user.get('authVersion', 0):
        raise HTTPException(401, 'Session expirée ou compte indisponible.')
    if user.get('requiresPasswordChange') and request.url.path not in ('/api/auth/me', '/api/auth/change-password'):
        raise HTTPException(403, 'Vous devez définir votre propre mot de passe avant de continuer.')
    return user


def require_role(*roles):
    def check(user=Depends(authenticated_user)):
        if user.get('role') not in roles and user.get('role') != 'admin':
            raise HTTPException(403, 'Vous ne possédez pas les autorisations nécessaires.')
        return user
    return check


def require_site(user, site_code):
    if user.get('role') != 'admin' and site_code not in user.get('siteCodes', []):
        raise HTTPException(403, 'Accès refusé à ce site de production.')


def public_user(user):
    return {'id': user['_id'], 'name': user['name'], 'email': user['email'], 'role': user['role'], 'site_codes': user.get('siteCodes', []),
            'disabled': user.get('disabled', False), 'must_change_password': user.get('requiresPasswordChange', False)}


def normalize_login_email(value: str) -> str:
    # Identifiant interne : .test est permis en DEVELOPPEMENT (EmailStr le refuse).
    # Nous vérifions la structure, mais ne prétendons pas vérifier la délivrabilité.
    import re
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError('Adresse e-mail incorrecte (format attendu : nom@domaine.tld).')
    return value


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_login_email(value)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=2, max_length=80)
    password: str | None = Field(default=None, min_length=12)
    role: str = Field(default='production')
    site_codes: list[str] = Field(default_factory=lambda: ['S01'])

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_login_email(value)


@router.post('/login')
def login(body: LoginBody, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    user = database(request).users.find_one({'email': str(body.email).lower(), 'disabled': {'$ne': True}})
    if user is None:
        raise HTTPException(401, 'Identifiants incorrects.')
    try:
        passwords.verify(user['passwordHash'], body.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, 'Identifiants incorrects.')
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({'sub': user['_id'], 'exp': expires, 'v': user.get('authVersion', 0)}, secret(), algorithm='HS256')
    return {'access_token': token, 'token_type': 'bearer', 'user': public_user(user)}


@router.get('/me')
def me(user=Depends(authenticated_user)):
    return public_user(user)


@router.post('/users', status_code=201)
def create_user(body: UserCreate, request: Request, response: Response, actor=Depends(require_role('admin'))):
    response.headers['Cache-Control'] = 'no-store'
    if body.role not in ROLES:
        raise HTTPException(422, 'Rôle inconnu.')
    if not body.site_codes or any(not c.strip() for c in body.site_codes):
        raise HTTPException(422, 'Sélectionnez au moins un site.')
    for code in body.site_codes:
        if not database(request).sites.find_one({'code': code}):
            raise HTTPException(422, f'Site inconnu : {code}')
    temporary_password = body.password or token_urlsafe(18)
    row = {'_id': str(uuid4()), 'email': str(body.email).lower(), 'name': body.name.strip(),
           'passwordHash': passwords.hash(temporary_password), 'role': body.role,
           'siteCodes': sorted(set(body.site_codes)), 'createdBy': actor['_id'],
           'disabled': False, 'requiresPasswordChange': True, 'authVersion': 0}

    try:
        database(request).users.insert_one(row)
    except DuplicateKeyError:
        raise HTTPException(409, 'Adresse e-mail déjà enregistrée.')
    database(request).access_audit.insert_one({'actorId': actor['_id'], 'targetId': row['_id'],
        'action': 'CREER_UTILISATEUR', 'role': row['role'], 'at': datetime.now(timezone.utc)})
    return {**public_user(row), 'temporary_password': temporary_password}


@router.get('/users')
def list_users(request: Request, actor=Depends(require_role('admin'))):
    return [public_user(u) for u in database(request).users.find({}, {'passwordHash': 0}).sort('name', 1)]


class UserUpdate(BaseModel):
    role: str | None = None
    site_codes: list[str] | None = None
    disabled: bool | None = None


@router.patch('/users/{user_id}')
def update_user(user_id: str, body: UserUpdate, request: Request, actor=Depends(require_role('admin'))):
    db = database(request)
    target = db.users.find_one({'_id': user_id})
    if not target:
        raise HTTPException(404, 'Collaborateur introuvable.')
    changes = {}
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, 'Rôle inconnu.')
        changes['role'] = body.role
    if body.site_codes is not None:
        codes = sorted(set(body.site_codes))
        if not codes:
            raise HTTPException(422, 'Sélectionnez au moins un site.')
        for code in codes:
            if not db.sites.find_one({'code': code}):
                raise HTTPException(422, f'Site inconnu : {code}')
        changes['siteCodes'] = codes
    if body.disabled is not None:
        changes['disabled'] = body.disabled
    if not changes:
        raise HTTPException(422, 'Aucune modification demandée.')
    if user_id == actor['_id'] and ('disabled' in changes and changes['disabled'] or
            ('role' in changes and changes['role'] != 'admin')):
        raise HTTPException(409, 'Vous ne pouvez pas désactiver ou rétrograder votre propre compte administrateur.')
    if target.get('role') == 'admin' and not target.get('disabled', False) and (
        changes.get('role', 'admin') != 'admin' or changes.get('disabled', False)):
        if db.users.count_documents({'role': 'admin', 'disabled': {'$ne': True}}) <= 1:
            raise HTTPException(409, 'Impossible de supprimer le dernier compte administrateur actif.')
    changes['updatedAt'] = datetime.now(timezone.utc)
    db.users.update_one({'_id': user_id}, {'$set': changes})
    db.access_audit.insert_one({'actorId': actor['_id'], 'targetId': user_id,
        'action': 'MODIFIER_UTILISATEUR', 'fields': [k for k in changes if k != 'updatedAt'],
        'at': datetime.now(timezone.utc)})
    return public_user(db.users.find_one({'_id': user_id}))


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=256)


@router.post('/change-password')
def change_password(body: PasswordChange, request: Request, user=Depends(authenticated_user)):
    try:
        passwords.verify(user['passwordHash'], body.current_password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, 'Mot de passe actuel incorrect.')
    if body.current_password == body.new_password:
        raise HTTPException(422, 'Le nouveau mot de passe doit être différent.')
    db = database(request)
    db.users.update_one({'_id': user['_id'], 'disabled': {'$ne': True}},
        {'$set': {'passwordHash': passwords.hash(body.new_password),
                  'requiresPasswordChange': False, 'passwordChangedAt': datetime.now(timezone.utc)},
         '$inc': {'authVersion': 1}})
    db.access_audit.insert_one({'actorId': user['_id'], 'targetId': user['_id'],
        'action': 'CHANGER_MOT_DE_PASSE', 'at': datetime.now(timezone.utc)})
    return {'message': 'Mot de passe changé. Reconnectez-vous avec le nouveau mot de passe.'}
