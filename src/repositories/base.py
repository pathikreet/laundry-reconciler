"""
Task: DATA-002 - Data Access Layer (Repository Pattern)
Description: Generic base repository implementation.
PRD Section: 5.1 Local data store (Abstraction)
"""

from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session
from src.db.base import Base

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    """
    Generic repository providing standard CRUD operations for any SQLAlchemy model.

    This abstracts direct database session management from the business logic.
    It ensures consistent access patterns and simplifies testing.

    Attributes:
        session: The active database session.
        model: The SQLAlchemy model class this repository manages.
    """

    def __init__(self, session: Session, model: Type[T]):
        """
        Initializes the repository with a session and model type.

        Args:
            session: SQLAlchemy session object.
            model: The model class (e.g., Order, PaymentEvent).
        """
        self.session = session
        self.model = model

    def get(self, id: int) -> Optional[T]:
        """Retrieves a single entity by its primary key ID."""
        return self.session.query(self.model).filter(self.model.id == id).first()

    def get_all(self) -> List[T]:
        """Retrieves all entities of this type."""
        return self.session.query(self.model).all()

    def create(self, obj: T) -> T:
        """
        Persists a new entity to the database.

        Commits the transaction and refreshes the object to populate generated fields (like ID).
        """
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def update(self, obj: T) -> T:
        """
        Updates an existing entity.

        Merges the object state into the session and commits.
        """
        self.session.merge(obj)
        self.session.commit()
        return obj

    def delete(self, id: int) -> bool:
        """
        Deletes an entity by its ID.

        Performs a safe delete that rolls back if cascade/integrity
        constraints are violated, preventing orphaned records.

        Returns:
            True if deleted, False if not found.

        Raises:
            DatabaseError: If the delete violates integrity constraints.
        """
        from src.exceptions import DatabaseError
        obj = self.get(id)
        if obj:
            try:
                self.session.delete(obj)
                self.session.commit()
                return True
            except Exception as e:
                self.session.rollback()
                raise DatabaseError(
                    f"Cannot delete {self.model.__name__} with id={id}: "
                    f"integrity constraint violated. Check for dependent records.",
                    details={"model": self.model.__name__, "id": id, "error": str(e)}
                )
        return False
