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


def _conn_returning(row):
    """构造一个 mock 连接:cursor(row_factory=dict_row) 上下文里 execute().fetchone() 返回 row。

    处理器不再改写共享连接的 row_factory,而是按查询开 dict_row cursor,故 mock 走 cursor 路径。
    """
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.return_value.fetchone.return_value = row
    return conn


def test_process_upserts_resource_document():
    conn = _conn_returning({
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record",
        "title": "减脂笔记", "summary": None, "content_text": "正文", "resource_version": 1})
    index = MagicMock()
    p = MeiliProcessor(conn=conn, index=index, config=MeiliConfig(state="enabled", url="u", api_key="k"))
    result = asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert result.status == "succeeded"
    doc = index.upsert.call_args[0][0]
    assert doc["resource_id"] == "r1"
    assert doc["title"] == "减脂笔记"
    assert doc["tenant_id"] == "default"
    assert doc["resource_version"] == 1


def test_process_missing_resource_id_is_permanent():
    p = MeiliProcessor(conn=MagicMock(), index=MagicMock(),
                       config=MeiliConfig(state="enabled", url="u", api_key="k"))
    try:
        asyncio.run(p.process(_item({"version": 1}), _Lease()))
        assert False, "should raise"
    except PermanentProcessingError:
        pass


def test_process_deletes_document_when_resource_gone():
    """资源已从核心库消失(查得 None):物理删除 Meili 文档,使检索引擎与核心库一致,
    而非仅标记 superseded 却把文档永久留在索引里。"""
    conn = _conn_returning(None)
    index = MagicMock()
    p = MeiliProcessor(conn=conn, index=index, config=MeiliConfig(state="enabled", url="u", api_key="k"))
    result = asyncio.run(p.process(_item({"resource_id": "gone-1", "version": 3}), _Lease()))
    assert result.status == "superseded"
    index.delete.assert_called_once_with("gone-1")
    index.upsert.assert_not_called()


def test_process_ensures_index_settings_once_before_upsert():
    conn = _conn_returning({
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record",
        "title": "t", "summary": None, "content_text": "body", "resource_version": 1})
    index = MagicMock()
    p = MeiliProcessor(conn=conn, index=index, config=MeiliConfig(state="enabled", url="u", api_key="k"))
    # 两次 process:ensure_index 只应调用一次(实例级幂等),每次都 upsert
    asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert index.ensure_index.call_count == 1
    assert index.upsert.call_count == 2


def test_process_supersedes_stale_or_candidate_version_without_deleting_current_document():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.return_value.fetchone.side_effect = [None, {"exists": 1}]
    index = MagicMock()
    processor = MeiliProcessor(
        conn=conn,
        index=index,
        config=MeiliConfig(state="enabled", url="u", api_key="k"),
    )

    result = asyncio.run(
        processor.process(_item({"resource_id": "r1", "version": 1}), _Lease())
    )

    assert result.status == "superseded"
    index.delete.assert_not_called()
    index.upsert.assert_not_called()
