"""
Task: IMP-001 - CRM Sales Export Parser
Description: Parser for CRM Excel/CSV exports.
PRD Section: 2.1 CRM sales export (Excel/CSV)
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime
from src.importers.base import BaseImporter
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.config.settings import settings
import dateutil.parser

class CRMImporter(BaseImporter):
    """
    Implements the import logic for CRM Sales & Delivery exports.

    This parser handles:
    - Reading Excel/CSV files.
    - Mapping columns to Order entities.
    - Normalizing dates, amounts, and payment modes.
    - Creating separate Order, PaymentEvent, and DeliveryEvent records.
    - Handling 'Adjustments' as returns/reversals.

    Attributes:
        session: SQLAlchemy session.
        run_id: The current reconciliation run ID.
    """

    def parse_file(self, file_path: str, column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Reads the CRM export file and normalizes it.

        Args:
            file_path: Path to the CRM export file.
            column_mapping: Mapping of internal field names to file column headers.
                            Required keys: order_number, order_date, customer_name,
                            order_amount, payment_received, payment_mode.

        Returns:
            List of dictionaries containing normalized order data.
        """
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")

        # Validate required columns
        required_cols = ["order_number", "order_date", "customer_name", "order_amount"]
        for key in required_cols:
            if key not in column_mapping or column_mapping[key] not in df.columns:
                 # Check if the column is present in the dataframe but not mapped
                 # If mapped but not in df, raise error
                 if key in column_mapping and column_mapping[key] not in df.columns:
                     raise ValueError(f"Required column '{column_mapping[key]}' not found in file.")
                 elif key not in column_mapping:
                     raise ValueError(f"Mapping for required field '{key}' is missing.")

        normalized_data = []
        for index, row in df.iterrows():
            try:
                # 1. Basic Order Info
                order_data = {
                    "order_number": str(row[column_mapping["order_number"]]).strip(),
                    "customer_name": str(row[column_mapping["customer_name"]]).strip(),
                    "order_date": self._parse_date(row.get(column_mapping["order_date"])),
                    "order_amount": self._parse_amount(row.get(column_mapping["order_amount"])),
                    "payment_received": self._parse_amount(row.get(column_mapping.get("payment_received"), 0)),
                    "adjustments": self._parse_amount(row.get(column_mapping.get("adjustments"), 0)),
                    "balance": self._parse_amount(row.get(column_mapping.get("balance"), 0)),
                    "raw_data": row.to_dict()
                }

                # 2. Payment Info
                payment_mode_raw = str(row.get(column_mapping.get("payment_mode"), "")).strip()
                order_data["payment_mode"] = self._normalize_payment_mode(payment_mode_raw)
                order_data["original_mode"] = payment_mode_raw

                payment_date_raw = row.get(column_mapping.get("payment_date"))
                order_data["payment_date"] = self._parse_date(payment_date_raw) if payment_date_raw else None

                # 3. Delivery Info
                delivery_date_raw = row.get(column_mapping.get("delivery_date"))
                order_data["delivery_date"] = self._parse_date(delivery_date_raw) if delivery_date_raw else None

                normalized_data.append(order_data)
            except Exception as e:
                # Log parsing error for this row but continue
                print(f"Error parsing row {index}: {e}")
                continue

        return normalized_data

    def persist_data(self, data: List[Dict[str, Any]]) -> int:
        """
        Saves parsed CRM data to the database.

        This method handles idempotency: if an order already exists, it updates it.
        It also creates associated PaymentEvent and DeliveryEvent records.
        """
        count = 0
        for item in data:
            # 1. Create/Update Order
            existing_order = self.session.query(Order).filter_by(order_number=item["order_number"]).first()
            if existing_order:
                # Update existing order
                existing_order.customer_name = item["customer_name"]
                existing_order.order_amount = item["order_amount"]
                existing_order.payment_received = item["payment_received"]
                existing_order.adjustments = item["adjustments"]
                existing_order.balance = item["balance"]
                existing_order.updated_at = datetime.now()
                order = existing_order
            else:
                order = Order(
                    order_number=item["order_number"],
                    customer_name=item["customer_name"],
                    order_date=item["order_date"],
                    order_amount=item["order_amount"],
                    payment_received=item["payment_received"],
                    adjustments=item["adjustments"],
                    balance=item["balance"],
                    raw_data=item["raw_data"]
                )
                self.session.add(order)
                self.session.flush() # Get ID

            # 2. Create PaymentEvent (if applicable)
            # Create a payment event if amount > 0 OR if explicit payment date exists
            if item["payment_received"] > 0 or item["payment_date"]:
                # Check for duplicate payment event?
                # For MVP, we might just re-create or check if one exists for this order/date/amount
                # Simple check: same order, same date, same amount
                payment_date = item["payment_date"] or item["order_date"] # Fallback to order date if paid immediately

                existing_payment = self.session.query(PaymentEvent).filter(
                    PaymentEvent.order_id == order.id,
                    PaymentEvent.payment_date == payment_date,
                    PaymentEvent.amount == item["payment_received"]
                ).first()

                if not existing_payment:
                    payment = PaymentEvent(
                        order_id=order.id,
                        source="crm",
                        payment_date=payment_date,
                        amount=item["payment_received"],
                        payment_mode=item["payment_mode"],
                        original_mode=item["original_mode"],
                        raw_data=item["raw_data"]
                    )
                    self.session.add(payment)

            # 3. Create DeliveryEvent (if applicable)
            if item["delivery_date"]:
                existing_delivery = self.session.query(DeliveryEvent).filter(
                    DeliveryEvent.order_id == order.id,
                    DeliveryEvent.delivery_date == item["delivery_date"]
                ).first()

                if not existing_delivery:
                    delivery = DeliveryEvent(
                        order_id=order.id,
                        source="crm",
                        delivery_date=item["delivery_date"],
                        customer_name=item["customer_name"],
                        raw_data=item["raw_data"]
                    )
                    self.session.add(delivery)

            count += 1

        self.session.commit()
        return count

    def _parse_date(self, date_val: Any) -> Optional[datetime.date]:
        """Parses date from various formats."""
        if pd.isna(date_val) or date_val == "":
            return None
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, pd.Timestamp):
            return date_val.date()
        try:
            return dateutil.parser.parse(str(date_val)).date()
        except:
            return None

    def _parse_amount(self, amount_val: Any) -> float:
        """Parses numeric amount, handling currency symbols."""
        if pd.isna(amount_val) or amount_val == "":
            return 0.0
        if isinstance(amount_val, (int, float)):
            return float(amount_val)
        try:
            # Remove currency symbols and commas
            clean_val = str(amount_val).replace('₹', '').replace(',', '').strip()
            return float(clean_val)
        except:
            return 0.0

    def _normalize_payment_mode(self, mode_raw: str) -> str:
        """Normalizes payment mode string using configured mapping."""
        mode_lower = mode_raw.lower()
        mapping = settings.payment_mode_mapping

        # Check explicit mapping
        if mode_lower in mapping:
            return mapping[mode_lower]

        # Check partial matches
        for key, value in mapping.items():
            if key in mode_lower:
                return value

        return "Other"
