import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.services.reconciliation import ReconciliationService
from src.models.orders import Order
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.cash_register import CashRegisterEntry
from src.models.exceptions import OrderException
from src.models.reconciliation import ReconciliationRun

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

def test_reconciliation_credit_policy(session):
    # Setup Order (Unpaid)
    # We need to flush/commit to get IDs for relationships
    order = Order(
        order_number='ORD-CREDIT', customer_name='Alice',
        order_date=date(2023, 11, 1), order_amount=100.0,
        raw_data={}
    )
    session.add(order)
    session.flush()

    # Notepad Delivery (Delivered today)
    delivery = DeliveryEvent(
        order_id=order.id, # Needs to be linked already
        source='notepad',
        delivery_date=date(2023, 11, 5),
        amount_collected=0.0,
        payment_mode='Cash'
    )
    session.add(delivery)
    # relationship update happens via foreign key or explicit append, flushing helps
    session.commit()

    service = ReconciliationService(session)
    run = service.run_reconciliation(run_date=date(2023, 11, 5))

    # Expect Credit Policy Violation Exception
    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='CreditPolicyViolation'
    ).first()

    assert exception is not None
    assert exception.severity == 'high'

def test_reconciliation_delivery_mismatch(session):
    # Setup Order (Delivered in Notepad, but raw_data doesn't have Delivery Date)
    order = Order(
        order_number='ORD-DEL-MIS', customer_name='Bob',
        order_date=date(2023, 11, 1), order_amount=100.0,
        raw_data={} # No 'Delivery Date'
    )
    session.add(order)
    session.flush()

    delivery = DeliveryEvent(
        order_id=order.id,
        source='notepad',
        delivery_date=date(2023, 11, 5),
        amount_collected=100.0,
        payment_mode='Cash'
    )
    session.add(delivery)
    session.commit()

    service = ReconciliationService(session)
    run = service.run_reconciliation(run_date=date(2023, 11, 5))

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='DeliveredNotMarkedCRM'
    ).first()

    assert exception is not None

def test_reconciliation_gpay_mismatch(session):
    run_date = date(2023, 11, 6)

    # CRM GPay: 500
    crm_p = PaymentEvent(source='crm', payment_date=run_date, amount=500.0, payment_mode='GPay')
    session.add(crm_p)

    # MSWIPE GPay: 400 (Missing 100)
    mswipe_p = PaymentEvent(source='mswipe', payment_date=run_date, amount=400.0, payment_mode='GPay')
    session.add(mswipe_p)
    session.commit()

    service = ReconciliationService(session)
    run = service.run_reconciliation(run_date=run_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        exception_type='GPayMismatch'
    ).first()

    assert exception is not None
    assert exception.evidence['diff'] == 100.0

def test_reconciliation_cash_variance(session):
    run_date = date(2023, 11, 7)

    # Expected Cash (Notepad): 1000
    delivery = DeliveryEvent(
        source='notepad', delivery_date=run_date,
        amount_collected=1000.0, payment_mode='Cash'
    )
    session.add(delivery)

    # Cash Register Derived: 800 (Short 200)
    register = CashRegisterEntry(
        entry_date=run_date,
        derived_cash_from_orders=800.0
    )
    session.add(register)
    session.commit()

    service = ReconciliationService(session)
    run = service.run_reconciliation(run_date=run_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        exception_type='CashVariance'
    ).first()

    assert exception is not None
    assert exception.evidence['diff'] == -200.0
