from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session
from src.db.base import Base

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model

    def get(self, id: int) -> Optional[T]:
        return self.session.query(self.model).filter(self.model.id == id).first()

    def get_all(self) -> List[T]:
        return self.session.query(self.model).all()

    def create(self, obj: T) -> T:
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def update(self, obj: T) -> T:
        self.session.merge(obj)
        self.session.commit()
        return obj

    def delete(self, id: int) -> bool:
        obj = self.get(id)
        if obj:
            self.session.delete(obj)
            self.session.commit()
            return True
        return False
