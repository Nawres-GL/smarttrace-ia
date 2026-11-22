"""API contract regression for .test user IDs and predictable login HTTP errors."""
import pytest
pytest.importorskip('pymongo')
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth import router, passwords


class FakeUsers:
    def __init__(self):
        self.row={'_id':'admin-1', 'email':'admin@example.test','name':'Admin test',
                  'role':'admin','siteCodes':['S01'],'passwordHash':passwords.hash('local-password-123')}
    def find_one(self, query):
        return self.row if query.get('email') == self.row['email'] else None


def test_login_contract(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','test-secret-abcdefghijklmnopqrstuvwxyz-0123456789')
    app=FastAPI()
    app.state.db=type('FakeDB',(),{'users':FakeUsers()})()
    app.include_router(router)
    cli=TestClient(app)
    assert cli.post('/api/auth/login',json={'email':'ADMIN@example.test','password':'local-password-123'}).status_code==200
    assert cli.post('/api/auth/login',json={'email':'admin@example.test','password':'incorrect'}).status_code==401
    assert cli.post('/api/auth/login',json={'email':'invalid','password':'local-password-123'}).status_code==422
