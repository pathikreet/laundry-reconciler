"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Unified payment event entity for CRM, MSWIPE, and Notepad.
PRD Section: 3.3 Storage model (PaymentEvent)
"""

from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order

class PaymentEvent(Base):
    """
    Represents a payment transaction from any source (CRM, MSWIPE, or Manual).

    This model unifies payment data to support reconciliation across multiple sources.
    It tracks the origin, amount, date, and linkage to specific orders.

    Attributes:
        source: Where the payment came from ('crm', 'mswipe', 'notepad').
        payment_date: Date the payment was made. Crucial for day-bucketing.
        amount: The monetary value of the payment.
        payment_mode: Normalized payment mode (e.g., 'GPay', 'Cash').
        original_mode: The raw mode string from the source (for audit).
        online_txn_id: Transaction ID for digital payments (Paytm linking).
        mswipe_ref_ids: JSON array of reference IDs from MSWIPE for linking.
        confidence_score: Calculated score for the match (0.00-1.00).
        match_evidence: JSON detailing why this payment was linked to an order.
    """
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

    # Relationship to the Order this payment is for
    order = relationship("Order", back_populates="payments")

    def __repr__(self):
        return f"<PaymentEvent(id={self.id}, source='{self.source}', amount={self.amount}, mode='{self.payment_mode}', date={self.payment_date})>"

# Add back relationship to Order
Order.payments = relationship("PaymentEvent", back_populates="order")
