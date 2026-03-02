"""
Tests for CRM Sales Report Importer.

Covers:
- normalize: column mapping, date parsing, amount parsing
- validate: summary row filtering
- save: multi-row order aggregation, PaymentEvent creation
- integration: end-to-end import from CSV file
"""
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
        'Payment Received': '1200',
        'Payment Mode': 'GPay',
        'Payment Date': '2023-10-26',
        'Adjustments': 0,
        'Balance': 0,
    }]

    normalized = importer.normalize(raw_data)
    assert len(normalized) == 1
    row = normalized[0]
    assert row['order_number'] == 'ORD-001'
    assert row['customer_name'] == 'John Doe'
    assert row['order_date'] == date(2023, 10, 26)
    assert row['payment_received'] == 1200.0
    assert row['balance'] == 0.0
    assert row['payment_mode'] == 'GPay'
    assert row['payment_date'] == date(2023, 10, 26)


def test_crm_importer_normalize_missing_amount(session):
    """When 'Payment Amount' is used instead of 'Payment Received', it should still work."""
    importer = CRMImporter(session)
    raw_data = [{
        'Order Number': 'ORD-001B',
        'Customer Name': 'Joe',
        'Order Date': '2023-10-26',
        'Payment Amount': '500',
        'Payment Mode': 'Cash',
        'Payment Date': '2023-10-26',
        'Adjustments': 0,
        'Balance': 0,
    }]
    normalized = importer.normalize(raw_data)
    assert normalized[0]['payment_received'] == 500.0


def test_crm_importer_validate_filters_summary(session):
    """Summary rows with no parseable order_date should be silently filtered out."""
    importer = CRMImporter(session)
    data = [
        {'order_number': 'T100', 'order_date': date(2023, 10, 26), 'payment_received': 100, 'raw_data': {}},
        {'order_number': '218', 'order_date': None, 'payment_received': 0, 'raw_data': {'Order Date': 'Total Order'}},
    ]
    valid = importer.validate(data)
    assert len(valid) == 1
    assert valid[0]['order_number'] == 'T100'
    assert len(importer.errors) == 0  # summary rows silently skipped, not counted as errors


def test_crm_importer_save(session):
    importer = CRMImporter(session)
    data = [{
        'order_number': 'ORD-002',
        'customer_name': 'Jane Doe',
        'customer_code': None,
        'customer_address': None,
        'customer_mobile': None,
        'order_date': date(2023, 10, 27),
        'payment_received': 500.0,
        'adjustments': 0.0,
        'balance': 0.0,
        'payment_mode': 'Cash',
        'payment_date': date(2023, 10, 27),
        'type': 'Order',
        'raw_data': {}
    }]

    importer.save(data)

    order = session.query(Order).filter_by(order_number='ORD-002').first()
    assert order is not None
    assert order.customer_name == 'Jane Doe'
    assert float(order.order_amount) == 500.0
    assert float(order.balance) == 0.0

    payment = session.query(PaymentEvent).filter_by(order_id=order.id).first()
    assert payment is not None
    assert float(payment.amount) == 500.0
    assert payment.source == 'crm'


def test_crm_importer_multi_row_aggregation(session):
    """Two payment rows for the same order should create 1 Order + 2 PaymentEvents."""
    importer = CRMImporter(session)
    data = [
        {
            'order_number': 'T697',
            'customer_name': 'Test Customer',
            'customer_code': None, 'customer_address': None, 'customer_mobile': None,
            'order_date': date(2025, 11, 7),
            'payment_received': 20.0,
            'adjustments': 0.0,
            'balance': 187.0,
            'payment_mode': 'Cash',
            'payment_date': date(2025, 11, 7),
            'type': 'Order',
            'raw_data': {'row': 1}
        },
        {
            'order_number': 'T697',
            'customer_name': 'Test Customer',
            'customer_code': None, 'customer_address': None, 'customer_mobile': None,
            'order_date': date(2025, 11, 7),
            'payment_received': 187.0,
            'adjustments': 0.0,
            'balance': 0.0,
            'payment_mode': 'Google Pay',
            'payment_date': date(2025, 11, 11),
            'type': 'Order',
            'raw_data': {'row': 2}
        },
    ]

    importer.save(data)

    order = session.query(Order).filter_by(order_number='T697').first()
    assert order is not None
    assert float(order.payment_received) == 207.0  # 20 + 187
    assert float(order.balance) == 0.0  # latest row
    assert float(order.order_amount) == 207.0  # 207 + 0 + 0

    payments = session.query(PaymentEvent).filter_by(order_id=order.id).all()
    assert len(payments) == 2
    amounts = sorted([float(p.amount) for p in payments])
    assert amounts == [20.0, 187.0]


def test_crm_importer_integration(session, tmp_path):
    csv_content = """Order Number,Customer Name,Order Date,Payment Received,Payment Mode,Payment Date,Adjustments,Balance
ORD-003,Alice Smith,2023-10-28,150.00,UPI,2023-10-28,0,0"""
    file_path = tmp_path / "test_crm.csv"
    file_path.write_text(csv_content, encoding='utf-8')

    importer = CRMImporter(session)
    importer.run(str(file_path))

    order = session.query(Order).filter_by(order_number='ORD-003').first()
    assert order is not None
    assert order.customer_name == 'Alice Smith'
    assert float(order.order_amount) == 150.0

    payment = session.query(PaymentEvent).filter_by(order_id=order.id).first()
    assert payment is not None
    assert payment.payment_mode == 'UPI'
