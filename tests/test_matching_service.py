import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.services.matching import MatchingService
from src.models.orders import Order
from src.models.deliveries import DeliveryEvent
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

def test_match_notepad_exact(session):
    # Setup
    order = Order(order_number='ORD-EXACT', customer_name='John Doe', order_date=date(2023, 10, 1), order_amount=100.0)
    session.add(order)

    delivery = DeliveryEvent(
        source='notepad',
        delivery_date=date(2023, 10, 5),
        customer_name='John Doe',
        amount_collected=100.0,
        raw_data={'Order Number': 'ORD-EXACT'}
    )
    session.add(delivery)
    session.commit()

    service = MatchingService(session)
    service.match_notepad_deliveries()

    assert delivery.order_id == order.id
    assert delivery.confidence_score == 1.0

def test_match_notepad_fuzzy(session):
    # Setup
    order = Order(order_number='ORD-FUZZY', customer_name='Jane Smith', order_date=date(2023, 10, 1), order_amount=200.0)
    session.add(order)

    # Delivery with no order number, but similar name and amount
    # Use a name that is close enough
    delivery = DeliveryEvent(
        source='notepad',
        delivery_date=date(2023, 10, 3), # within window
        customer_name='Jane Smithy',
        amount_collected=200.0,
        raw_data={}
    )
    session.add(delivery)
    session.commit()

    service = MatchingService(session)
    service.match_notepad_deliveries()

    assert delivery.order_id == order.id
    assert delivery.confidence_score > 0.8

def test_match_mswipe_crm_gpay(session):
    # Setup
    order = Order(order_number='ORD-GPAY', customer_name='Bob', order_date=date(2023, 10, 10), order_amount=500.0)
    session.add(order)
    session.flush()

    # CRM Payment
    crm_payment = PaymentEvent(
        order_id=order.id,
        source='crm',
        payment_date=date(2023, 10, 12),
        amount=500.0,
        payment_mode='GPay'
    )
    session.add(crm_payment)

    # MSWIPE Payment (unlinked)
    mswipe_payment = PaymentEvent(
        source='mswipe',
        payment_date=date(2023, 10, 12),
        amount=500.0,
        payment_mode='GPay'
    )
    session.add(mswipe_payment)
    session.commit()

    service = MatchingService(session)
    service.match_mswipe_payments()

    assert mswipe_payment.order_id == order.id
    assert float(mswipe_payment.confidence_score) == 0.9
