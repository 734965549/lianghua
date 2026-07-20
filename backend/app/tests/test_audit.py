import pytest

from app.repositories.audit_repo import AuditRepository
from app.services.audit_service import AuditService


@pytest.mark.integration
def test_audit_write_and_list(db):
    svc = AuditService(db, correlation_id="test_audit_001")
    svc.log(
        action="test_action",
        module="test_module",
        object_type="test_object",
        object_id="obj-1",
        result="success",
        reason="单元测试",
        request_summary={"key": "value"},
    )
    db.commit()

    repo = AuditRepository(db)
    items, total = repo.list_paginated(page=1, page_size=10, module="test_module", action="test_action")
    assert total >= 1
    hit = next(i for i in items if i.correlation_id == "test_audit_001")
    assert hit.result == "success"
    assert hit.request_summary == {"key": "value"}
