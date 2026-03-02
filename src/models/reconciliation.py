"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Reconciliation run entity for tracking processing status and results.
PRD Section: 3.3 Storage model (ReconciliationRun)
"""

from sqlalchemy import Column, Integer, String, Date, JSON, DateTime, func
from sqlalchemy.orm import relationship
from src.db.base import Base

class ReconciliationRun(Base):
    """
    Represents a single execution of the reconciliation process for a specific date.

    This model serves as a snapshot of the reconciliation state.
    It links all exceptions and audit logs generated during a run.

    Attributes:
        run_date: The calendar date being reconciled.
        status: The current state of the run ('pending', 'complete', 'failed').
        config_snapshot: A copy of the configuration used for this run (for reproducibility).
        summary_stats: Aggregated statistics (e.g., total orders, match rate) stored as JSON.
        started_at: When the run began.
        completed_at: When the run finished (if successful).
    """
    __tablename__ = 'reconciliation_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default='pending')  # pending, complete, failed
    config_snapshot = Column(JSON, nullable=True)
    summary_stats = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=False, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ReconciliationRun(id={self.id}, date={self.run_date}, status='{self.status}')>"
