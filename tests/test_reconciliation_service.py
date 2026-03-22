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
from src.config.settings import Settings

# Test settings with no date boundaries (so all checks run for any date)
test_settings = Settings(
    notepad_start_date=None,
    cash_register_start_date=None,
)

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

    service = ReconciliationService(session, settings=test_settings)
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

    service = ReconciliationService(session, settings=test_settings)
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

    service = ReconciliationService(session, settings=test_settings)
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

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=run_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        exception_type='CashVariance'
    ).first()

    assert exception is not None
    assert exception.evidence['diff'] == -200.0


# ── New Feature Tests ─────────────────────────────────────


def test_ageing_order_detected(session):
    """Feature 2: Order > 10 days old with no delivery → AgeingOrder exception."""
    order = Order(
        order_number='ORD-AGEING-1', customer_name='Charlie',
        order_date=date(2023, 10, 1), order_amount=500.0,
        raw_data={}
    )
    session.add(order)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=date(2023, 10, 20))

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='AgeingOrder'
    ).first()

    assert exception is not None
    assert exception.severity == 'high'
    assert exception.evidence['days_since_order'] == 19


def test_ageing_order_not_flagged_if_delivered(session):
    """Feature 2: Order > 10 days old WITH delivery → no AgeingOrder."""
    order = Order(
        order_number='ORD-AGEING-2', customer_name='Diana',
        order_date=date(2023, 10, 1), order_amount=200.0,
        raw_data={}
    )
    session.add(order)
    session.flush()

    delivery = DeliveryEvent(
        order_id=order.id, source='notepad',
        delivery_date=date(2023, 10, 5),
        amount_collected=200.0, payment_mode='Cash'
    )
    session.add(delivery)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=date(2023, 10, 20))

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='AgeingOrder'
    ).first()

    assert exception is None


def test_notepad_payment_not_in_crm(session):
    """Feature 3: Notepad has payment but CRM has none → NotepadPaymentNotInCRM."""
    run_date = date(2023, 12, 1)

    order = Order(
        order_number='ORD-NP-NOCRM', customer_name='Eve',
        order_date=date(2023, 12, 1), order_amount=300.0,
        raw_data={}
    )
    session.add(order)
    session.flush()

    # Notepad payment (no CRM payment exists for this order)
    notepad_pay = PaymentEvent(
        order_id=order.id, source='notepad',
        payment_date=run_date, amount=300.0,
        payment_mode='Cash'
    )
    session.add(notepad_pay)

    # Also need a delivery or payment event on run_date so order is visible
    delivery = DeliveryEvent(
        order_id=order.id, source='notepad',
        delivery_date=run_date,
        amount_collected=300.0, payment_mode='Cash'
    )
    session.add(delivery)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=run_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='NotepadPaymentNotInCRM'
    ).first()

    assert exception is not None
    assert exception.severity == 'high'
    assert exception.evidence['notepad_amount'] == 300.0


def test_gpay_order_mismatch(session):
    """Feature 1: CRM GPay payment but no MSWIPE linked → GPayOrderMismatch."""
    run_date = date(2023, 12, 2)

    order = Order(
        order_number='ORD-GPAY-NOMSWIPE', customer_name='Frank',
        order_date=date(2023, 12, 2), order_amount=400.0,
        raw_data={}
    )
    session.add(order)
    session.flush()

    crm_pay = PaymentEvent(
        order_id=order.id, source='crm',
        payment_date=run_date, amount=400.0,
        payment_mode='GPay'
    )
    session.add(crm_pay)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=run_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='GPayOrderMismatch'
    ).first()

    assert exception is not None
    assert exception.severity == 'medium'
    assert exception.evidence['missing_source'] == 'MSWIPE'


def test_backdated_gpay_detected(session):
    """Feature 4: MSWIPE exists on earlier date for CRM GPay → BackdatedGPayPayment."""
    crm_date = date(2023, 12, 10)
    mswipe_date = date(2023, 12, 3)  # Payment actually received earlier

    order = Order(
        order_number='ORD-BACKDATED-GPAY', customer_name='Grace',
        order_date=date(2023, 12, 1), order_amount=250.0,
        raw_data={}
    )
    session.add(order)
    session.flush()

    # CRM records GPay on Dec 10
    crm_pay = PaymentEvent(
        order_id=order.id, source='crm',
        payment_date=crm_date, amount=250.0,
        payment_mode='GPay'
    )
    session.add(crm_pay)

    # MSWIPE received it on Dec 3 (unlinked—not assigned to this order)
    mswipe_pay = PaymentEvent(
        source='mswipe',
        payment_date=mswipe_date, amount=250.0,
        payment_mode='GPay'
    )
    session.add(mswipe_pay)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=crm_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        order_id=order.id,
        exception_type='BackdatedGPayPayment'
    ).first()

    assert exception is not None
    assert exception.severity == 'medium'
    assert exception.evidence['days_offset'] == 7
    assert exception.evidence['mswipe_actual_date'] == str(mswipe_date)


def test_cash_surplus_deficit_correlation(session):
    """Feature 4: Cash deficit today + surplus on earlier date → SuspectedBackdatedCashPayment."""
    deficit_date = date(2024, 2, 2)
    surplus_date = date(2023, 12, 14)

    # Surplus date: register has 1234 MORE than notepad says
    register_surplus = CashRegisterEntry(
        entry_date=surplus_date,
        derived_cash_from_orders=2234.0  # register has extra
    )
    session.add(register_surplus)
    # Notepad cash on surplus day: 1000 (surplus = 2234 - 1000 = 1234)
    surplus_delivery = DeliveryEvent(
        source='notepad', delivery_date=surplus_date,
        amount_collected=1000.0, payment_mode='Cash'
    )
    session.add(surplus_delivery)
    surplus_payment = PaymentEvent(
        source='notepad', payment_date=surplus_date,
        amount=1000.0, payment_mode='Cash'
    )
    session.add(surplus_payment)

    # Deficit date: notepad says 1234 cash, register says 0
    deficit_delivery = DeliveryEvent(
        source='notepad', delivery_date=deficit_date,
        amount_collected=1234.0, payment_mode='Cash'
    )
    session.add(deficit_delivery)
    deficit_payment = PaymentEvent(
        source='notepad', payment_date=deficit_date,
        amount=1234.0, payment_mode='Cash'
    )
    session.add(deficit_payment)
    register_deficit = CashRegisterEntry(
        entry_date=deficit_date,
        derived_cash_from_orders=0.0  # register has nothing
    )
    session.add(register_deficit)
    session.commit()

    service = ReconciliationService(session, settings=test_settings)
    run = service.run_reconciliation(run_date=deficit_date)

    exception = session.query(OrderException).filter_by(
        reconciliation_run_id=run.id,
        exception_type='SuspectedBackdatedCashPayment'
    ).first()

    assert exception is not None
    assert exception.severity == 'medium'
    assert exception.evidence['surplus_date'] == str(surplus_date)


def test_period_summary_nets_out_variances(session):
    """Feature 5: Opposite GPay variances in period → net = 0, self-correcting."""
    day_a = date(2024, 1, 10)
    day_b = date(2024, 1, 15)

    # Day A: CRM GPay 500, MSWIPE 300 (crm > mswipe by 200)
    session.add(PaymentEvent(source='crm', payment_date=day_a, amount=500.0, payment_mode='GPay'))
    session.add(PaymentEvent(source='mswipe', payment_date=day_a, amount=300.0, payment_mode='GPay'))

    # Day B: CRM GPay 300, MSWIPE 500 (mswipe > crm by 200)
    session.add(PaymentEvent(source='crm', payment_date=day_b, amount=300.0, payment_mode='GPay'))
    session.add(PaymentEvent(source='mswipe', payment_date=day_b, amount=500.0, payment_mode='GPay'))
    session.commit()

    # Run daily reconciliation for both days first
    service = ReconciliationService(session, settings=test_settings)
    service.run_reconciliation(run_date=day_a)
    service.run_reconciliation(run_date=day_b)

    # Period summary should show net = 0
    summary = service.get_period_summary(date(2024, 1, 1), date(2024, 1, 31))

    assert summary['net_gpay_variance'] == 0.0
    assert summary['self_correcting_pairs'] > 0
