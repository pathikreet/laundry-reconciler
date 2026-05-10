"""
Package transaction records from the CRM Package Sales report.

Tracks package purchases (initial sales) and recharges (wallet top-ups).
These represent real money inflows (cash or MSWIPE) that appear in the
register/MSWIPE totals but are recorded as "Package" in CRM, not as
Cash or Online — a key reconciliation adjustment.
"""

from sqlalchemy import Column, Integer, String, Date, Numeric, JSON, DateTime, func
from src.db.base import Base


class PackageTransaction(Base):
    """
    Represents a package sale or recharge event.

    When a customer buys or recharges a prepaid wallet (Package),
    they pay via cash or MSWIPE. This payment shows up in the
    register or MSWIPE machine but CRM records subsequent order
    payments as "Package" (wallet deduction).

    Attributes:
        customer_name: Customer who purchased/recharged the package.
        customer_code: CRM customer code (from insights file, if available).
        mobile: Customer mobile (from insights file, if available).
        package_name: Package type (e.g., "Smart2000: 10% Savings").
        transaction_type: 'Sale' (new purchase) or 'Recharge' (top-up).
        amount: The amount paid (₹).
        transaction_date: When the sale/recharge occurred.
        payment_mode: Inferred payment mode ('Cash' or 'Online').
        staff: Staff who processed the transaction.
        raw_data: Original row from the import file.
    """
    __tablename__ = 'package_transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String, nullable=False, index=True)
    customer_code = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    package_name = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)  # Sale or Recharge
    amount = Column(Numeric(10, 2), nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    payment_mode = Column(String, nullable=True)  # Inferred: Cash or Online
    staff = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return (
            f"<PackageTransaction(id={self.id}, customer='{self.customer_name}', "
            f"type='{self.transaction_type}', amount={self.amount}, "
            f"date={self.transaction_date})>"
        )
