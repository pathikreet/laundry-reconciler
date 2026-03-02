import pytest
from datetime import date
from src.models.orders import Order


def test_create_order(session):
    """Test basic Order creation and retrieval."""
    new_order = Order(
        order_number="ORD-DB-001",
        customer_name="Test Customer",
        order_date=date(2023, 1, 1),
        order_amount=100.0
    )
    session.add(new_order)
    session.commit()

    retrieved_order = session.query(Order).filter_by(order_number="ORD-DB-001").first()
    assert retrieved_order is not None
    assert retrieved_order.customer_name == "Test Customer"
    assert float(retrieved_order.order_amount) == 100.0


def test_order_defaults(session):
    """Test that default values are applied correctly."""
    order = Order(
        order_number="ORD-DB-002",
        customer_name="Default Test",
        order_date=date(2023, 1, 2),
        order_amount=200.0
    )
    session.add(order)
    session.commit()

    assert float(order.payment_received) == 0.0
    assert float(order.adjustments) == 0.0
    assert float(order.balance) == 0.0
    assert order.type == 'Order'


def test_order_repr(session):
    """Test that __repr__ returns useful debug string."""
    order = Order(
        order_number="ORD-DB-003",
        customer_name="Repr Test",
        order_date=date(2023, 1, 3),
        order_amount=300.0
    )
    session.add(order)
    session.flush()

    repr_str = repr(order)
    assert "ORD-DB-003" in repr_str
    assert "Repr Test" in repr_str
