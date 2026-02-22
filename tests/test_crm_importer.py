import pytest
import os
import pandas as pd
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.crm import CRMImporter
from src.models.orders import Order
from src.models.payments import PaymentEvent

@pytest.fixture(scope="module")
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine

@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

def test_crm_importer_normalize(session):
    importer = CRMImporter(session)
    raw_data = [{
        'Order Number': 'ORD-001',
        'Customer Name': 'John Doe',
        'Order Date': '2023-10-26',
        'Order Amount': '1,200.00',
        'Payment Amount': '1200',
        'Payment Mode': 'GPay',
        'Payment Date': '2023-10-26'
    }]

    normalized = importer.normalize(raw_data)
    assert len(normalized) == 1
    row = normalized[0]
    assert row['order_number'] == 'ORD-001'
    assert row['customer_name'] == 'John Doe'
    assert row['order_date'] == date(2023, 10, 26)
    assert row['order_amount'] == 1200.0
    assert row['payment_received'] == 1200.0
    assert row['balance'] == 0.0
    assert row['payment_mode'] == 'GPay'
    assert row['payment_date'] == date(2023, 10, 26)

def test_crm_importer_save(session):
    importer = CRMImporter(session)
    data = [{
        'order_number': 'ORD-002',
        'customer_name': 'Jane Doe',
        'order_date': date(2023, 10, 27),
        'delivery_date': None,
        'order_amount': 500.0,
        'payment_received': 500.0,
        'adjustments': 0.0,
        'balance': 0.0,
        'payment_mode': 'Cash',
        'payment_date': date(2023, 10, 27),
        'raw_data': {}
    }]

    importer.save(data)

    order = session.query(Order).filter_by(order_number='ORD-002').first()
    assert order is not None
    assert order.customer_name == 'Jane Doe'
    assert order.balance == 0.0

    payment = session.query(PaymentEvent).filter_by(order_id=order.id).first()
    assert payment is not None
    assert payment.amount == 500.0
    assert payment.source == 'crm'

def test_crm_importer_integration(session, tmp_path):
    # Create a dummy CSV file
    csv_content = """Order Number,Customer Name,Order Date,Order Amount,Payment Amount,Payment Mode,Payment Date
ORD-003,Alice Smith,2023-10-28,150.00,150.00,UPI,2023-10-28"""
    file_path = tmp_path / "test_crm.csv"
    file_path.write_text(csv_content, encoding='utf-8')

    importer = CRMImporter(session)
    importer.run(str(file_path))

    order = session.query(Order).filter_by(order_number='ORD-003').first()
    assert order is not None
    assert order.customer_name == 'Alice Smith'

    payment = session.query(PaymentEvent).filter_by(order_id=order.id).first()
    assert payment is not None
    assert payment.payment_mode == 'UPI'
