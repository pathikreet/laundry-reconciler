import pytest
from datetime import date
from src.repositories.orders import OrderRepository
from src.repositories.payments import PaymentEventRepository
from src.repositories.deliveries import DeliveryEventRepository
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent


def test_order_repository_create_and_get(session):
    """Test OrderRepository CRUD."""
    repo = OrderRepository(session)
    order = Order(
        order_number="ORD-REPO-001",
        customer_name="Repo Customer",
        order_date=date(2023, 1, 2),
        order_amount=200.0
    )
    repo.create(order)

    retrieved = repo.get_by_order_number("ORD-REPO-001")
    assert retrieved is not None
    assert retrieved.customer_name == "Repo Customer"


def test_order_repository_get_by_date_range(session):
    """Test date-range query on OrderRepository."""
    repo = OrderRepository(session)
    order1 = Order(order_number="ORD-DATE-001", customer_name="A", order_date=date(2023, 3, 1), order_amount=100.0)
    order2 = Order(order_number="ORD-DATE-002", customer_name="B", order_date=date(2023, 3, 15), order_amount=200.0)
    order3 = Order(order_number="ORD-DATE-003", customer_name="C", order_date=date(2023, 4, 1), order_amount=300.0)
    session.add_all([order1, order2, order3])
    session.commit()

    results = repo.get_by_date_range(date(2023, 3, 1), date(2023, 3, 31))
    order_numbers = [o.order_number for o in results]
    assert "ORD-DATE-001" in order_numbers
    assert "ORD-DATE-002" in order_numbers
    assert "ORD-DATE-003" not in order_numbers


def test_order_repository_get_nonexistent(session):
    """Test that getting a nonexistent order returns None."""
    repo = OrderRepository(session)
    result = repo.get_by_order_number("DOES-NOT-EXIST")
    assert result is None


def test_payment_repository_get_by_date(session):
    """Test PaymentEventRepository date filter."""
    repo = PaymentEventRepository(session)
    payment = PaymentEvent(
        source="crm",
        payment_date=date(2023, 5, 1),
        amount=150.0,
        payment_mode="Cash"
    )
    session.add(payment)
    session.commit()

    results = repo.get_by_date(date(2023, 5, 1))
    assert len(results) >= 1
    assert any(float(p.amount) == 150.0 for p in results)


def test_delivery_repository_unlinked(session):
    """Test querying unlinked deliveries directly via session."""
    delivery = DeliveryEvent(
        source="notepad",
        delivery_date=date(2023, 5, 1),
        customer_name="Unlinked Customer",
        amount_collected=200.0,
        raw_data={}
    )
    session.add(delivery)
    session.commit()

    # Query unlinked deliveries directly (no get_unlinked method on repo)
    unlinked = session.query(DeliveryEvent).filter(
        DeliveryEvent.order_id == None
    ).all()
    assert any(d.customer_name == "Unlinked Customer" for d in unlinked)
