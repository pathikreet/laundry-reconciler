from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order
from src.models.reconciliation import ReconciliationRun

class OrderException(Base):
    __tablename__ = 'order_exceptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reconciliation_run_id = Column(Integer, ForeignKey('reconciliation_runs.id'), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True, index=True)  # NULL for day-level
    severity = Column(String, nullable=False, index=True)  # high, medium, low
    exception_type = Column(String, nullable=False)
    reason_tags = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=True)
    suggested_action = Column(String, nullable=True)
    resolution_status = Column(String, nullable=False, default='open', index=True)  # open, resolved, false_positive
    resolution_note = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    reconciliation_run = relationship("ReconciliationRun", back_populates="exceptions")
    order = relationship("Order", back_populates="exceptions")

ReconciliationRun.exceptions = relationship("OrderException", back_populates="reconciliation_run")
Order.exceptions = relationship("OrderException", back_populates="order")
