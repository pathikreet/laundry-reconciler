from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.orders import Order
from src.db.base import Base

class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: Session):
        super().__init__(session, Order)

    def get_by_order_number(self, order_number: str) -> Optional[Order]:
        return self.session.query(Order).filter(Order.order_number == order_number).first()

    def get_by_date_range(self, start_date: str, end_date: str) -> List[Order]:
        return self.session.query(Order).filter(Order.order_date.between(start_date, end_date)).all()
