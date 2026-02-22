import pytest
import os
import pandas as pd
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.notepad import NotepadImporter
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.orders import Order

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

def test_notepad_importer_normalize(session):
    importer = NotepadImporter(session)
    raw_data = [{
        'Date': '2023-10-26',
        'Amount': '500.00',
        'Mode': 'Cash',
        'Order Number': 'ORD-001',
        'Customer Name': 'John',
        'Runner': 'Mike',
        'Notes': 'Delivered'
    }]

    normalized = importer.normalize(raw_data)
    assert len(normalized) == 1
    row = normalized[0]
    assert row['delivery_date'] == date(2023, 10, 26)
    assert row['amount_collected'] == 500.0
    assert row['payment_mode'] == 'Cash'
    assert row['order_number'] == 'ORD-001'
    assert row['runner_name'] == 'Mike'

def test_notepad_importer_save(session):
    # Setup order
    order = Order(order_number='ORD-001', customer_name='John', order_date=date(2023, 10, 20))
    session.add(order)
    session.commit()

    importer = NotepadImporter(session)
    data = [{
        'delivery_date': date(2023, 10, 26),
        'amount_collected': 500.0,
        'payment_mode': 'Cash',
        'order_number': 'ORD-001',
        'customer_name': 'John',
        'runner_name': 'Mike',
        'notes': 'Delivered',
        'raw_data': {}
    }]

    importer.save(data)

    delivery = session.query(DeliveryEvent).filter_by(order_id=order.id).first()
    assert delivery is not None
    assert delivery.source == 'notepad'
    assert delivery.runner_name == 'Mike'

    payment = session.query(PaymentEvent).filter_by(order_id=order.id, source='notepad').first()
    assert payment is not None
    assert payment.amount == 500.0
    assert payment.payment_mode == 'Cash'
