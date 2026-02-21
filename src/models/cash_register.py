from sqlalchemy import Column, Integer, Date, Numeric, JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.reconciliation import ReconciliationRun

class CashRegisterEntry(Base):
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

    reconciliation_run = relationship("ReconciliationRun", back_populates="cash_entries")

ReconciliationRun.cash_entries = relationship("CashRegisterEntry", back_populates="reconciliation_run")
