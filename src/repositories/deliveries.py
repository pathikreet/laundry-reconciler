from typing import List
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.deliveries import DeliveryEvent
from src.db.base import Base

class DeliveryEventRepository(BaseRepository[DeliveryEvent]):
    def __init__(self, session: Session):
        super().__init__(session, DeliveryEvent)

    def get_by_date(self, date: str) -> List[DeliveryEvent]:
        return self.session.query(DeliveryEvent).filter(DeliveryEvent.delivery_date == date).all()

    def get_by_order_id(self, order_id: int) -> List[DeliveryEvent]:
        return self.session.query(DeliveryEvent).filter(DeliveryEvent.order_id == order_id).all()
