"""
Task: DATA-002 - Data Access Layer (PaymentEventRepository)
Description: Data access for payment events.
PRD Section: 3.3 Storage model (PaymentEvent)
"""

from typing import List
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.payments import PaymentEvent
from src.db.base import Base

class PaymentEventRepository(BaseRepository[PaymentEvent]):
    """
    Handles all database operations related to Payment Events.

    This repository supports cross-source payment data (CRM, MSWIPE, Notepad).
    It is crucial for linking payments to orders across multiple dates (PRD 3.5).

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the PaymentEvent model."""
        super().__init__(session, PaymentEvent)

    def get_by_date(self, date: str) -> List[PaymentEvent]:
        """
        Retrieves all payments made on a specific date.

        This is used for 'Day-Level Totals' validation (RECON-005).

        Args:
            date: Date string (YYYY-MM-DD).
        """
        return self.session.query(PaymentEvent).filter(PaymentEvent.payment_date == date).all()

    def get_by_order_id(self, order_id: int) -> List[PaymentEvent]:
        """
        Retrieves all payments linked to a specific order.

        This supports the 'Order Mini-Ledger' (RECON-001) by finding all payments
        for an order, including advances and partial payments.

        Args:
            order_id: The database ID of the Order.
        """
        return self.session.query(PaymentEvent).filter(PaymentEvent.order_id == order_id).all()
