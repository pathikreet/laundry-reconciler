"""
Shared test fixtures for the Laundry Reconciler test suite.
All tests use in-memory SQLite for speed and isolation.
"""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.audit import AuditLog
from src.models.cash_register import CashRegisterEntry
from src.models.config import ColumnMapping, ToleranceConfig


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite engine shared across the test session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """
    Provide a transactional session that rolls back after each test.
    This ensures complete test isolation without leftover data.
    """
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_order(session):
    """Create a sample order for testing."""
    order = Order(
        order_number="ORD-TEST-001",
        customer_name="Test Customer",
        order_date=date(2023, 11, 1),
        order_amount=500.0,
        payment_received=500.0,
        balance=0.0,
        payment_mode="Cash",
        raw_data={"source": "test"}
    )
    session.add(order)
    session.flush()
    return order


@pytest.fixture
def sample_payment(session, sample_order):
    """Create a sample payment event linked to the sample order."""
    payment = PaymentEvent(
        order_id=sample_order.id,
        source="crm",
        payment_date=date(2023, 11, 1),
        amount=500.0,
        payment_mode="Cash"
    )
    session.add(payment)
    session.flush()
    return payment


@pytest.fixture
def sample_delivery(session, sample_order):
    """Create a sample delivery event linked to the sample order."""
    delivery = DeliveryEvent(
        order_id=sample_order.id,
        source="notepad",
        delivery_date=date(2023, 11, 5),
        customer_name="Test Customer",
        amount_collected=500.0,
        payment_mode="Cash",
        runner_name="Test Runner",
        raw_data={"source": "test"}
    )
    session.add(delivery)
    session.flush()
    return delivery
