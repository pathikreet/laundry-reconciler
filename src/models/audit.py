"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Audit log entity for tracking system changes and user actions.
PRD Section: 5.2 Auditability
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.reconciliation import ReconciliationRun

class AuditLog(Base):
    """
    Records a history of actions performed in the system for accountability.

    This immutable log tracks imports, matches, overrides, and resolutions.
    It stores the 'before' and 'after' state for critical changes.

    Attributes:
        reconciliation_run_id: The run associated with this action (optional).
        action_type: What happened ('import', 'match', 'override', 'resolve').
        entity_type: What was affected ('order', 'payment', 'exception').
        entity_id: The ID of the affected entity.
        old_value: JSON snapshot of the state before the action.
        new_value: JSON snapshot of the state after the action.
        performed_by: The user or system component responsible.
        performed_at: When the action occurred.
    """
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reconciliation_run_id = Column(Integer, ForeignKey('reconciliation_runs.id'), nullable=True, index=True)
    action_type = Column(String, nullable=False)  # import, match, override, resolve
    entity_type = Column(String, nullable=False)  # order, payment, exception
    entity_id = Column(Integer, nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    performed_by = Column(String, nullable=True, default='system')
    performed_at = Column(DateTime, nullable=False, default=func.now())

    # Relationship to the Run
    reconciliation_run = relationship("ReconciliationRun", back_populates="audit_logs")

# Add back relationship
ReconciliationRun.audit_logs = relationship("AuditLog", back_populates="reconciliation_run")
