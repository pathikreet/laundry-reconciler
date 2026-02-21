"""
Task: DATA-002 - Data Access Layer (OrderRepository)
Description: Data access for CRM orders.
PRD Section: 3.3 Storage model (Order)
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.orders import Order
from src.db.base import Base

class OrderRepository(BaseRepository[Order]):
    """
    Handles all database operations related to CRM Orders.

    This repository extends the base CRUD operations with order-specific queries.
    It supports the matching engine by providing methods to find orders by number or date.

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the Order model."""
        super().__init__(session, Order)

    def get_by_order_number(self, order_number: str) -> Optional[Order]:
        """
        Retrieves a single order by its unique CRM order number.

        This is the primary method used for 'Exact Order Matching' (MATCH-001).

        Args:
            order_number: The unique string identifier (e.g., 'ORD-2023-001').
        """
        return self.session.query(Order).filter(Order.order_number == order_number).first()

    def get_by_date_range(self, start_date: str, end_date: str) -> List[Order]:
        """
        Retrieves all orders placed within a specific date range.

        This is used during reconciliation runs to fetch the relevant dataset.

        Args:
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).
        """
        return self.session.query(Order).filter(Order.order_date.between(start_date, end_date)).all()
