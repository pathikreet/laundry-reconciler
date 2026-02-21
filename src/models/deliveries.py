from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order

class DeliveryEvent(Base):
    __tablename__ = 'delivery_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True, index=True)
    source = Column(String, nullable=False)  # 'crm', 'notepad'
    delivery_date = Column(Date, nullable=False, index=True)
    customer_name = Column(String, nullable=True)
    amount_collected = Column(Numeric(10, 2), nullable=True)
    payment_mode = Column(String, nullable=True)
    runner_name = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    confidence_score = Column(Numeric(3, 2), nullable=True)
    match_evidence = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    order = relationship("Order", back_populates="deliveries")

Order.deliveries = relationship("DeliveryEvent", back_populates="order")
