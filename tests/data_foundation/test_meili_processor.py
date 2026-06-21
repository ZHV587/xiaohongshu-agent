import asyncio
from unittest.mock import MagicMock
from datetime import datetime, timezone

from data_foundation.processors.meili import MeiliProcessor
from data_foundation.processors.base import PermanentProcessingError
from data_foundation.models import OutboxItem
from data_foundation.engine_config import MeiliConfig


def _item(payload):
    now = datetime.now(timezone.utc)
    return OutboxItem(id="i1", tenant_id="default", resource_id=payload.get("resource_id"),
        resource_version=payload.get("version"), topic="meili_index", dedupe_key="d",
        payload=payload, status="processing", attempts=1, next_attempt_at=now,
        lease_owner="w", lease_expires_at=now, error_code=None, error_summary=None,
        dead_at=None, created_at=now, updated_at=now)


class _Lease:
    async def assert_owned(self):
        return None


def test_state_disabled_when_no_config():
    p = MeiliProcessor(conn=MagicMock(), index=MagicMock(),
                       config=MeiliConfig(state="disabled", url="", api_key=""))
    assert p.state().status == "disabled"
    assert p.state().reason_code == "MEILI_CONFIG_MISSING"


def test_process_upserts_resource_document():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record",
        "title": "减脂笔记", "summary": None, "content_text": "正文"}
    index = MagicMock()
    p = MeiliProcessor(conn=conn, index=index, config=MeiliConfig(state="enabled", url="u", api_key="k"))
    result = asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert result.status == "succeeded"
    doc = index.upsert.call_args[0][0]
    assert doc["resource_id"] == "r1"
    assert doc["title"] == "减脂笔记"
    assert doc["tenant_id"] == "default"


def test_process_missing_resource_id_is_permanent():
    p = MeiliProcessor(conn=MagicMock(), index=MagicMock(),
                       config=MeiliConfig(state="enabled", url="u", api_key="k"))
    try:
        asyncio.run(p.process(_item({"version": 1}), _Lease()))
        assert False, "should raise"
    except PermanentProcessingError:
        pass
