from sqlalchemy import Column, Integer, String, Date, JSON, DateTime, func
from sqlalchemy.orm import relationship
from src.db.base import Base

class ReconciliationRun(Base):
    __tablename__ = 'reconciliation_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default='pending')  # pending, complete, failed
    config_snapshot = Column(JSON, nullable=True)
    summary_stats = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=False, default=func.now())
    completed_at = Column(DateTime, nullable=True)
