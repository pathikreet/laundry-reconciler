from typing import List
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.payments import PaymentEvent
from src.db.base import Base

class PaymentEventRepository(BaseRepository[PaymentEvent]):
    def __init__(self, session: Session):
        super().__init__(session, PaymentEvent)

    def get_by_date(self, date: str) -> List[PaymentEvent]:
        return self.session.query(PaymentEvent).filter(PaymentEvent.payment_date == date).all()

    def get_by_order_id(self, order_id: int) -> List[PaymentEvent]:
        return self.session.query(PaymentEvent).filter(PaymentEvent.order_id == order_id).all()
