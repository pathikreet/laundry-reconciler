"""
Expenses entity for tracking cash and online business expenses.

Enables accurate cash reconciliation by accounting for legitimate
expenses made from the cash register, which would otherwise show up
as "missing" cash during variance checks.
"""

from sqlalchemy import Column, Integer, Date, Numeric, String, JSON, DateTime, func
from src.db.base import Base


class Expense(Base):
    """
    Represents a single business expense entry.

    Attributes:
        expense_date: The calendar date the expense was made.
        amount: The expense amount in ₹.
        category: Classification (e.g. Supplies, Utility, Transport, Misc).
        description: Free-text description of what was purchased.
        mode: Payment mode (Cash, Online, Card) — determines which
              reconciliation checks are adjusted.
        paid_to: Vendor or recipient name (optional).
        raw_data: Original values from the import file.
    """
    __tablename__ = 'expenses'

    id = Column(Integer, primary_key=True, autoincrement=True)
    expense_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    category = Column(String, nullable=True)
    description = Column(String, nullable=True)
    mode = Column(String, nullable=False, default='Cash')  # Cash, Online, Card
    paid_to = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return (
            f"<Expense(id={self.id}, date={self.expense_date}, "
            f"amount={self.amount}, mode={self.mode}, "
            f"category={self.category})>"
        )
