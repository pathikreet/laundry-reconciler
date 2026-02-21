from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from src.db.base import Base
from src.models.reconciliation import ReconciliationRun

class AuditLog(Base):
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

    reconciliation_run = relationship("ReconciliationRun", back_populates="audit_logs")

ReconciliationRun.audit_logs = relationship("AuditLog", back_populates="reconciliation_run")
