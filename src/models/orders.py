from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, func
from src.db.base import Base

class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_number = Column(String, unique=True, nullable=False, index=True)
    customer_code = Column(String, nullable=True)
    customer_name = Column(String, nullable=False, index=True)
    customer_address = Column(String, nullable=True)
    customer_mobile = Column(String, nullable=True)
    order_date = Column(Date, nullable=False, index=True)
    order_amount = Column(Numeric(10, 2), nullable=False, default=0)
    payment_received = Column(Numeric(10, 2), nullable=False, default=0)
    adjustments = Column(Numeric(10, 2), nullable=False, default=0)
    balance = Column(Numeric(10, 2), nullable=False, default=0)
    type = Column(String, nullable=True, default='Order')
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
