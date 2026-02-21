"""
Task: DATA-002 - Data Access Layer (ReconciliationRepository)
Description: Data access for reconciliation runs, exceptions, and audit logs.
PRD Section: 3.3 Storage model (ReconciliationRun, OrderException, AuditLog)
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.audit import AuditLog
from src.db.base import Base

class ReconciliationRepository(BaseRepository[ReconciliationRun]):
    """
    Handles all database operations related to Reconciliation Runs.

    This repository manages the lifecycle of a reconciliation run, including
    logging exceptions and audit events.

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the ReconciliationRun model."""
        super().__init__(session, ReconciliationRun)

    def get_by_date(self, date: str) -> Optional[ReconciliationRun]:
        """
        Retrieves a reconciliation run for a specific calendar date.

        This is used to check if a run has already occurred or to resume one.

        Args:
            date: Date string (YYYY-MM-DD).
        """
        return self.session.query(ReconciliationRun).filter(ReconciliationRun.run_date == date).first()

    def get_latest(self) -> Optional[ReconciliationRun]:
        """
        Retrieves the most recently created reconciliation run.

        This is useful for displaying the latest status in the UI.
        """
        return self.session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).first()

    def add_exception(self, exception: OrderException):
        """
        Persists a new OrderException linked to a run.

        This records specific issues (e.g., amount mismatch) found during reconciliation (RECON-003).

        Args:
            exception: The OrderException object.
        """
        self.session.add(exception)
        self.session.commit()

    def add_audit_log(self, audit_log: AuditLog):
        """
        Persists a new AuditLog entry.

        This records system actions for accountability (PRD 5.2).

        Args:
            audit_log: The AuditLog object.
        """
        self.session.add(audit_log)
        self.session.commit()
