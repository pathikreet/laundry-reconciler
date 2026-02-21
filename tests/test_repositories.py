import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.repositories.orders import OrderRepository
from src.models.orders import Order
from datetime import date
import os

@pytest.fixture(scope="module")
def engine():
    db_path = "test_repo.db"
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

def test_order_repository(session):
    repo = OrderRepository(session)
    order = Order(order_number="ORD002", customer_name="Repo Customer", order_date=date(2023, 1, 2), order_amount=200.0)
    repo.create(order)

    retrieved = repo.get_by_order_number("ORD002")
    assert retrieved is not None
    assert retrieved.customer_name == "Repo Customer"
