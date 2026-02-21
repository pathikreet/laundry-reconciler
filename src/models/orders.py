"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Core order entity representing CRM export data.
PRD Section: 2.1 CRM sales export
"""

from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, func
from src.db.base import Base

class Order(Base):
    """
    Represents a customer order from the CRM.

    This model stores normalized data from the CRM export.
    It includes fields for order details, customer information, and financial status.

    Attributes:
        order_number: Unique identifier from CRM. Indexed for fast lookups.
        customer_code: Customer code (optional).
        customer_name: Normalized customer name. Indexed for fuzzy matching.
        order_date: Date the order was placed. Indexed for date-range queries.
        order_amount: Total order value.
        payment_received: Amount marked as received in CRM (may be 0 if paid via advance).
        adjustments: Returns or reversals (PRD 2.1).
        balance: Outstanding balance according to CRM.
        type: Record type (default 'Order').
        raw_data: JSON storage for the original row data (auditability).
    """
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
