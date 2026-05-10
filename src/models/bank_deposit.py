"""
Bank deposit records extracted from the Cash Register spreadsheet.

Tracks cash-to-bank transfers that reduce the register's closing balance
without being a business expense. Used to adjust ``derived_cash_from_orders``
so it accurately reflects cash received from orders.
"""

from sqlalchemy import Column, Integer, Date, Numeric, String, JSON, DateTime, func
from src.db.base import Base


class BankDeposit(Base):
    """
    Represents a single cash-to-bank deposit event.

    These are extracted from the "Bank Deposits" section of the Cash Register
    Excel file (one table per year sheet). They explain large drops in the
    register's closing balance that are NOT expenses.

    Attributes:
        deposit_date: The calendar date the cash was deposited in the bank.
        amount: The deposit amount in ₹.
        month_label: The month label as written in the source (e.g. "November").
        raw_data: Original values from the import file.
    """
    __tablename__ = 'bank_deposits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    deposit_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    month_label = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return (
            f"<BankDeposit(id={self.id}, date={self.deposit_date}, "
            f"amount={self.amount})>"
        )
