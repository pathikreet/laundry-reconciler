import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.models.orders import Order
from src.db.init_db import init_db
from datetime import date
import os

@pytest.fixture(scope="module")
def engine():
    db_path = "test_laundry.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    yield engine
    os.remove(db_path)

@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_order(session):
    new_order = Order(order_number="ORD001", customer_name="Test Customer", order_date=date(2023, 1, 1), order_amount=100.0)
    session.add(new_order)
    session.commit()

    retrieved_order = session.query(Order).filter_by(order_number="ORD001").first()
    assert retrieved_order is not None
    assert retrieved_order.customer_name == "Test Customer"
    assert retrieved_order.order_amount == 100.0
