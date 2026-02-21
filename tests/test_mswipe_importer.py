import pytest
import os
import pandas as pd
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.mswipe import MSwipeImporter
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

def test_mswipe_importer_normalize(session):
    importer = MSwipeImporter(session)
    raw_data = [{
        'Status': 'Successful',
        'Amount': '150.50',
        'PaymentDate': '2023-10-26',
        'CardType': 'Visa',
        'RR_NO': '123456'
    }, {
        'Status': 'Failed',
        'Amount': '200.00',
        'PaymentDate': '2023-10-26',
        'CardType': 'MasterCard',
        'RR_NO': '789012'
    }]

    normalized = importer.normalize(raw_data)
    # Only successful transaction should be normalized
    assert len(normalized) == 1
    row = normalized[0]
    assert row['payment_date'] == date(2023, 10, 26)
    assert row['amount'] == 150.50
    assert row['payment_mode'] == 'Visa'
    assert row['ref_id'] == '123456'

def test_mswipe_importer_save(session):
    importer = MSwipeImporter(session)
    data = [{
        'payment_date': date(2023, 10, 27),
        'amount': 300.0,
        'payment_mode': 'UPI',
        'original_mode': 'UPI',
        'ref_id': 'REF001',
        'raw_data': {}
    }]

    importer.save(data)

    payment = session.query(PaymentEvent).filter_by(source='mswipe').first()
    assert payment is not None
    assert payment.amount == 300.0
    assert payment.payment_mode == 'GPay' # Should be normalized to GPay
    assert payment.mswipe_ref_ids == ['REF001']

def test_mswipe_importer_duplicate(session):
    importer = MSwipeImporter(session)
    data = [{
        'payment_date': date(2023, 10, 27),
        'amount': 300.0,
        'payment_mode': 'UPI',
        'original_mode': 'UPI',
        'ref_id': 'REF001',
        'raw_data': {}
    }]

    # Save twice
    importer.save(data)
    importer.save(data)

    payments = session.query(PaymentEvent).filter_by(source='mswipe').all()
    assert len(payments) == 1
