"""
Tests for Milestone 2: Import Pipeline
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.crm import CRMImporter
from src.importers.mswipe import MSwipeImporter
from src.importers.cash_register import CashRegisterImporter
from src.services.mapping_service import MappingService
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.cash_register import CashRegisterEntry
from datetime import date
import pandas as pd
import os

@pytest.fixture(scope="module")
def engine():
    db_path = "test_importers.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_crm_importer(session, tmp_path):
    # Create dummy CRM file
    df = pd.DataFrame({
        "Order No": ["ORD001", "ORD002"],
        "Date": ["2023-01-01", "2023-01-02"],
        "Customer": ["Alice", "Bob"],
        "Amount": [100, 200],
        "Received": [100, 0],
        "Mode": ["GPay", "Cash"]
    })
    file_path = tmp_path / "crm_test.csv"
    df.to_csv(file_path, index=False)

    importer = CRMImporter(session)
    mapping = {
        "order_number": "Order No",
        "order_date": "Date",
        "customer_name": "Customer",
        "order_amount": "Amount",
        "payment_received": "Received",
        "payment_mode": "Mode"
    }

    data = importer.parse_file(str(file_path), mapping)
    assert len(data) == 2
    assert data[0]["order_number"] == "ORD001"
    assert data[0]["payment_mode"] == "GPay"

    count = importer.persist_data(data)
    assert count == 2 # 2 orders processed (some might be updates, but logic counts processed items)

    # Verify DB
    order = session.query(Order).filter_by(order_number="ORD001").first()
    assert order is not None
    assert order.customer_name == "Alice"

def test_mswipe_importer(session, tmp_path):
    # Create dummy MSWIPE file
    df = pd.DataFrame({
        "Txn Date": ["2023-01-01 10:00:00", "2023-01-02 11:00:00"],
        "Amount": [100, 50], # 50 is small/fail scenario maybe?
        "Status": ["Success", "Fail"],
        "Mode": ["UPI", "Card"]
    })
    file_path = tmp_path / "mswipe_test.csv"
    df.to_csv(file_path, index=False)

    importer = MSwipeImporter(session)
    mapping = {
        "txn_date": "Txn Date",
        "amount": "Amount",
        "status": "Status",
        "payment_mode": "Mode"
    }

    data = importer.parse_file(str(file_path), mapping)
    assert len(data) == 1 # Only success row
    assert data[0]["amount"] == 100.0
    assert data[0]["payment_mode"] == "GPay" # Normalized

    count = importer.persist_data(data)
    assert count == 1

    # Verify DB
    event = session.query(PaymentEvent).filter_by(source="mswipe", amount=100.0).first()
    assert event is not None

def test_mapping_service(session):
    service = MappingService(session)

    # Test auto-detection
    cols = ["Order Number", "Date", "Customer Name", "Total Amount"]
    required = ["order_number", "order_date", "customer_name", "order_amount"]

    mapping = service.auto_detect_mapping(cols, required)
    assert mapping["order_number"] == "Order Number"
    assert mapping["order_amount"] == "Total Amount" # Fuzzy match 'Total' -> 'amount' heuristic

    # Test persistence
    service.save_mapping("Test Profile", "crm", mapping, is_default=True)
    saved = service.get_mapping("crm")
    assert saved == mapping
