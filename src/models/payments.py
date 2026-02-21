from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order

class PaymentEvent(Base):
    __tablename__ = 'payment_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True, index=True)
    source = Column(String, nullable=False)  # 'crm', 'mswipe', 'notepad'
    payment_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_mode = Column(String, nullable=False)
    original_mode = Column(String, nullable=True)
    online_txn_id = Column(String, nullable=True)
    accept_by = Column(String, nullable=True)
    payee_vpa = Column(String, nullable=True)
    mswipe_ref_ids = Column(JSON, nullable=True)
    confidence_score = Column(Numeric(3, 2), nullable=True)
    match_evidence = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    order = relationship("Order", back_populates="payments")

# Add back relationship to Order
Order.payments = relationship("PaymentEvent", back_populates="order")
