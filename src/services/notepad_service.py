"""
Task: IMP-004 - Runner Notepad Entry System
Description: Service for managing manual runner entries.
PRD Section: 2.2 Runner notepad (manual entry + optional OCR)
"""

from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.config.settings import settings

class NotepadService:
    """
    Manages manual entries from runners.

    Notepad entries can create both DeliveryEvents (confirming delivery)
    and PaymentEvents (confirming cash/payment collected).

    Attributes:
        session: SQLAlchemy session.
        run_id: The current reconciliation run ID.
    """

    def __init__(self, session: Session, run_id: int = None):
        self.session = session
        self.run_id = run_id

    def add_entry(self, entry_data: Dict[str, Any]) -> int:
        """
        Processes a single notepad line entry.

        Args:
            entry_data: Dictionary containing:
                - order_number (optional)
                - customer_name (optional)
                - amount_collected (required)
                - payment_mode (required)
                - delivery_date (optional, defaults to today)
                - runner_name (optional)
                - notes (optional)

        Returns:
            ID of the created DeliveryEvent (primary record).
        """
        # 1. Validation
        if not entry_data.get("amount_collected") and not entry_data.get("order_number"):
            raise ValueError("Entry must have amount collected or order number.")

        delivery_date = entry_data.get("delivery_date") or date.today()

        # 2. Create DeliveryEvent
        delivery = DeliveryEvent(
            source="notepad",
            delivery_date=delivery_date,
            customer_name=entry_data.get("customer_name"),
            amount_collected=entry_data.get("amount_collected"),
            payment_mode=entry_data.get("payment_mode"),
            runner_name=entry_data.get("runner_name"),
            notes=entry_data.get("notes"),
            raw_data=entry_data
        )
        self.session.add(delivery)
        self.session.flush() # Get ID

        # 3. Create PaymentEvent (if applicable)
        # If money was collected, this is a payment event too.
        # But we link it to the DeliveryEvent logically (or through Order later).
        # For MVP, we treat Notepad primarily as Delivery confirmation + Payment assertion.
        # The 'PaymentEvent' table unifies payments. Should we duplicate?
        # Yes, per PRD 3.3, PaymentEvent stores "from CRM payment rows and from MSWIPE".
        # It doesn't explicitly say Notepad entries go into PaymentEvent table, but 3.7.1 compares Notepad vs CRM.
        # It's cleaner to query one table for payments.

        if entry_data.get("amount_collected", 0) > 0:
            payment = PaymentEvent(
                source="notepad",
                payment_date=delivery_date,
                amount=entry_data["amount_collected"],
                payment_mode=settings.payment_mode_mapping.get(
                    entry_data.get("payment_mode", "").lower(), "Other"
                ),
                original_mode=entry_data.get("payment_mode"),
                accept_by=entry_data.get("runner_name"),
                raw_data=entry_data
            )
            self.session.add(payment)

        self.session.commit()
        return delivery.id
