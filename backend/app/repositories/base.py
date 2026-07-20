from typing import Generic, Type, TypeVar

from sqlalchemy.orm import Session

from app.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id) -> ModelT | None:
        return self.db.get(self.model, id)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def list(self, *, offset: int = 0, limit: int = 20, filters: dict | None = None):
        q = self.db.query(self.model)
        if filters:
            for k, v in filters.items():
                if v is not None:
                    q = q.filter(getattr(self.model, k) == v)
        return q.offset(offset).limit(limit).all()
