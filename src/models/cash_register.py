"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Cash register entry entity for daily cash reconciliation.
PRD Section: 2.4 Daily cash register Excel
"""

from sqlalchemy import Column, Integer, Date, Numeric, JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.reconciliation import ReconciliationRun

class CashRegisterEntry(Base):
    """
    Represents the daily cash balance recorded in the cash register.

    This model stores closing balances to derive the 'cash from orders' signal.
    It supports the calendar grid layout processing logic.

    Attributes:
        entry_date: The calendar date (unique).
        closing_balance: The recorded cash balance at day's end (C_d).
        prior_closing_balance: The previous day's balance (C_d-1), possibly from a recursive lookback.
        expenses_deposits: Manual adjustment for cash expenses/bank deposits (E_d).
        derived_cash_from_orders: Calculated signal: C_d - C_(d-1) + E_d.
        reconciliation_run_id: The run associated with this entry.
        validation_status: Indicates data completeness ('valid', 'partial', 'missing').
        raw_data: Original values from the Excel grid.
    """
    __tablename__ = 'cash_register_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_date = Column(Date, nullable=False, unique=True, index=True)
    closing_balance = Column(Numeric(10, 2), nullable=True)
    prior_closing_balance = Column(Numeric(10, 2), nullable=True)
    expenses_deposits = Column(Numeric(10, 2), nullable=True, default=0)
    derived_cash_from_orders = Column(Numeric(10, 2), nullable=True)
    reconciliation_run_id = Column(Integer, ForeignKey('reconciliation_runs.id'), nullable=True, index=True)
    validation_status = Column(String, nullable=True, default='valid')  # valid, partial, missing
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Relationship to the Run
    reconciliation_run = relationship("ReconciliationRun", back_populates="cash_entries")

# Add back relationship
ReconciliationRun.cash_entries = relationship("CashRegisterEntry", back_populates="reconciliation_run")
