"""Basic Pydantic field checks (full MongoDB workflow tested separately)."""
import pytest
pytest.importorskip('pymongo')
pytest.importorskip('qrcode')
from datetime import date
from pydantic import ValidationError
from app.main import ProductionLotIn
from app.operations import GerminationIn, GraftIn, QualityIn, DeliveryIn


def test_sowing_tray_fields_required():
    with pytest.raises(ValidationError):
        ProductionLotIn(site_code='S01',seed_lot_id='s1',quantity_sown=300,sown_on=date.today())


def test_germination_humidity_range():
    with pytest.raises(ValidationError):
        GerminationIn(quantity=1,location='CH-01',started_on=date.today(),ended_on=date.today(),
                      observed_on=date.today(),duration_hours=2,humidity=101)


def test_grafting_nonpositive_quantity():
    with pytest.raises(ValidationError):
        GraftIn(rootstock_lot_id='r',scion_location='CH-01',rootstock_location='CH-02',
                quantity_used=0,quantity_success=0,grafted_on=date.today())


def test_quality_requires_health_and_homogeneity():
    with pytest.raises(ValidationError):
        QualityIn(approved=True,inspected_quantity=30,approved_quantity=30,inspected_on=date.today(),notes='test')


def test_delivery_requires_client_receipt_confirmation_field():
    with pytest.raises(ValidationError):
        DeliveryIn(preparation_id='p1',quantity=10,delivery_note='BL123',transporter='ABC Transport',
                   vehicle='TR-001',received_by='Client',delivered_on=date.today())
