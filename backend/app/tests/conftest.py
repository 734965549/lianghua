import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.system_state import SystemState
from app.db.session import SessionLocal
from app.main import app
from app.schemas.enums import SystemStatus


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def reset_system_state(db: Session):
    """测试前后将 system_state 重置为 ready，避免污染开发库。"""

    def _reset():
        row = db.get(SystemState, 1)
        if row is None:
            row = SystemState(id=1, status=SystemStatus.READY, status_reason="test reset")
            db.add(row)
        else:
            row.status = SystemStatus.READY
            row.status_reason = "test reset"
        db.commit()
        return row

    row = _reset()
    yield row
    _reset()
