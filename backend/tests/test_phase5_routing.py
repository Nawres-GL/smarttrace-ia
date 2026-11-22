"""Regression: Phase 4 dropped /api/historique/overview accidentally."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.history import router as historical_router, overview
try:
    from app.main import app
except ModuleNotFoundError as exc:
    if exc.name != "pymongo":
        raise
    app = None


class OverviewTests(unittest.TestCase):
    @unittest.skipIf(app is None, "PyMongo not installed in test runtime")
    def test_route_is_registered(self):
        paths = {r.path for r in app.routes}
        self.assertIn('/api/historique/overview', paths)
        self.assertIn('/api/blockchain/status', paths)

    @unittest.skipIf(app is None, "PyMongo not installed in test runtime")
    def test_unauthenticated_request_does_not_return_404(self):
        with TestClient(app) as c:
            r = c.get('/api/historique/overview')
        self.assertEqual(r.status_code, 401)

    def test_overview_endpoint_serves_expected_dashboard_fields(self):
        # Isolated router check: auth is applied at main.py registration level,
        # which is exercised by the main-app integration test when PyMongo exists.
        isolated = FastAPI()
        isolated.include_router(historical_router)
        with patch('app.history.indexes', return_value=(
            [1, 2], [1, 2, 3], [1], {'13766': [1]},
            {'13766': [1, 2], '99999': [3]}, {'13766': [1]})):
            with TestClient(isolated) as client:
                result = client.get('/api/historique/overview')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['linked_lots'], 1)
        self.assertEqual(result.json()['delivery_lines_linked'], 2)

    def test_summary_uses_three_sources(self):
        with patch('app.history.indexes', return_value=(
            [1, 2], [1,2,3], [1], {'12345':[1]}, {'12345':[1,2], '54321':[3]}, {'12345':[1]})):
            x = overview()
        self.assertEqual(x['production_rows'], 2)
        self.assertEqual(x['linked_lots'], 1)
        self.assertEqual(x['delivery_lines_linked'], 2)
        self.assertEqual(x['grafting_rows'], 1)
