"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Exception entity for flagging issues found during reconciliation.
PRD Section: 3.9 Severity and explainability (Exception)
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.orders import Order
from src.models.reconciliation import ReconciliationRun

class OrderException(Base):
    """
    Represents an exception or anomaly detected during the reconciliation process.

    Exceptions are the primary output for users to act upon (e.g., unpaid orders, mismatches).
    They include severity levels, reasons, and suggested actions.

    Attributes:
        reconciliation_run_id: The run during which this exception was found.
        order_id: The specific order this exception relates to (optional for day-level issues).
        severity: 'high', 'medium', or 'low'.
        exception_type: A category string (e.g., 'AmountMismatch', 'UnpaidDelivery').
        reason_tags: A list of tags explaining the "why" (e.g., ['MissingPayment', 'WrongMode']).
        evidence: JSON data showing the conflicting values (e.g., CRM amount vs Notepad amount).
        suggested_action: Text guiding the user on how to resolve the issue.
        resolution_status: Tracks user action ('open', 'resolved', 'false_positive').
        resolution_note: Optional note added by the user when resolving.
    """
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

    # Relationships to the Run and Order
    reconciliation_run = relationship("ReconciliationRun", back_populates="exceptions")
    order = relationship("Order", back_populates="exceptions")

    def __repr__(self):
        return f"<OrderException(id={self.id}, type='{self.exception_type}', severity='{self.severity}', status='{self.resolution_status}')>"

# Add back relationships
ReconciliationRun.exceptions = relationship("OrderException", back_populates="reconciliation_run")
Order.exceptions = relationship("OrderException", back_populates="order")
