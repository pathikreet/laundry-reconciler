"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Delivery event entity from CRM and Notepad.
PRD Section: 3.3 Storage model (DeliveryEvent)
"""

from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order

class DeliveryEvent(Base):
    """
    Represents a delivery action, either from CRM or runner notepad.

    This model allows tracking deliveries separately from orders to detect discrepancies.
    A delivery event confirms that an order was fulfilled and potentially paid for.

    Attributes:
        source: Where the delivery record came from ('crm', 'notepad').
        delivery_date: When the delivery occurred.
        customer_name: The customer name associated with the delivery.
        amount_collected: The amount collected by the runner at delivery (Notepad only).
        payment_mode: The payment mode reported by the runner (Notepad only).
        runner_name: The person who made the delivery.
        notes: Any additional notes from the runner.
        match_evidence: JSON detailing why this delivery event matches an order.
    """
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

    # Relationship to the Order being delivered
    order = relationship("Order", back_populates="deliveries")

# Add back relationship to Order
Order.deliveries = relationship("DeliveryEvent", back_populates="order")
