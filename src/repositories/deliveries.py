"""
Task: DATA-002 - Data Access Layer (DeliveryEventRepository)
Description: Data access for delivery events.
PRD Section: 3.3 Storage model (DeliveryEvent)
"""

from typing import List
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.deliveries import DeliveryEvent
from src.db.base import Base

class DeliveryEventRepository(BaseRepository[DeliveryEvent]):
    """
    Handles all database operations related to Delivery Events.

    This repository supports tracking deliveries from CRM and Notepad.
    It is used to identify 'Delivered not marked in CRM' exceptions (RECON-002).

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the DeliveryEvent model."""
        super().__init__(session, DeliveryEvent)

    def get_by_date(self, date: str) -> List[DeliveryEvent]:
        """
        Retrieves all deliveries marked on a specific date.

        This is used for 'Delivery Day Close' processing (PRD 3.1).

        Args:
            date: Date string (YYYY-MM-DD).
        """
        return self.session.query(DeliveryEvent).filter(DeliveryEvent.delivery_date == date).all()

    def get_by_order_id(self, order_id: int) -> List[DeliveryEvent]:
        """
        Retrieves all delivery records for a specific order.

        This checks if an order has been marked as delivered in any source.

        Args:
            order_id: The database ID of the Order.
        """
        return self.session.query(DeliveryEvent).filter(DeliveryEvent.order_id == order_id).all()
