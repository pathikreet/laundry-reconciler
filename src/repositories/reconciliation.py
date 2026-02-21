from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.audit import AuditLog
from src.db.base import Base

class ReconciliationRepository(BaseRepository[ReconciliationRun]):
    def __init__(self, session: Session):
        super().__init__(session, ReconciliationRun)

    def get_by_date(self, date: str) -> Optional[ReconciliationRun]:
        return self.session.query(ReconciliationRun).filter(ReconciliationRun.run_date == date).first()

    def get_latest(self) -> Optional[ReconciliationRun]:
        return self.session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).first()

    def add_exception(self, exception: OrderException):
        self.session.add(exception)
        self.session.commit()

    def add_audit_log(self, audit_log: AuditLog):
        self.session.add(audit_log)
        self.session.commit()
