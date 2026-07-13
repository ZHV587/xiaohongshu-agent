import asyncio
import threading
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


def test_stale_exact_task_reconciles_the_resource_level_current_document():
    conn = _conn_returning(
        {
            "id": "r1",
            "tenant_id": "default",
            "type": "feishu_base_record",
            "title": "current-v2",
            "summary": None,
            "content_text": "current body",
            "resource_version": 2,
        }
    )
    index = MagicMock()
    processor = MeiliProcessor(
        conn=conn,
        index=index,
        config=MeiliConfig(state="enabled", url="u", api_key="k"),
    )

    result = asyncio.run(
        processor.process(_item({"resource_id": "r1", "version": 1}), _Lease())
    )

    assert result.status == "succeeded"
    index.delete.assert_not_called()
    assert index.upsert.call_args.args[0]["resource_version"] == 2


def test_process_deletes_stale_document_when_resource_has_no_current_knowledge_target():
    conn = _conn_returning(None)
    index = MagicMock()
    processor = MeiliProcessor(
        conn=conn,
        index=index,
        config=MeiliConfig(state="enabled", url="u", api_key="k"),
    )

    result = asyncio.run(
        processor.process(_item({"resource_id": "rejected-1", "version": 2}), _Lease())
    )

    assert result.status == "superseded"
    index.delete.assert_called_once_with("rejected-1")
    index.upsert.assert_not_called()


class _DynamicCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params):
        return self

    def fetchone(self):
        with self.connection.lock:
            current = self.connection.current
            return None if current is None else dict(current)


class _DynamicConnection:
    def __init__(self, current):
        self.current = current
        self.lock = threading.Lock()

    def cursor(self, **_kwargs):
        return _DynamicCursor(self)

    def set_current(self, current):
        with self.lock:
            self.current = current


class _BarrierIndex:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.operations = []

    def ensure_index(self):
        return None

    def _barrier_once(self):
        if not self.started.is_set():
            self.started.set()
            assert self.release.wait(timeout=2)

    def upsert(self, document):
        self.operations.append(("upsert", dict(document)))
        self._barrier_once()

    def delete(self, resource_id):
        self.operations.append(("delete", resource_id))
        self._barrier_once()


def _current_document(version=1):
    return {
        "id": "race-1",
        "tenant_id": "default",
        "type": "writing_teardown",
        "title": f"teardown-v{version}",
        "summary": None,
        "content_text": "body",
        "resource_version": version,
    }


def test_upsert_in_flight_then_withdrawn_is_rechecked_and_deleted():
    async def scenario():
        connection = _DynamicConnection(_current_document())
        index = _BarrierIndex()
        processor = MeiliProcessor(
            conn=connection,
            index=index,
            config=MeiliConfig(state="enabled", url="u", api_key="k"),
        )
        task = asyncio.create_task(
            processor.process(
                _item({"resource_id": "race-1", "version": 1}),
                _Lease(),
            )
        )
        assert await asyncio.to_thread(index.started.wait, 1)
        connection.set_current(None)
        index.release.set()
        return await task, index.operations

    result, operations = asyncio.run(scenario())

    assert result.status == "superseded"
    assert [operation[0] for operation in operations] == ["upsert", "delete"]


def test_delete_in_flight_then_restored_is_rechecked_and_upserted():
    async def scenario():
        connection = _DynamicConnection(None)
        index = _BarrierIndex()
        processor = MeiliProcessor(
            conn=connection,
            index=index,
            config=MeiliConfig(state="enabled", url="u", api_key="k"),
        )
        task = asyncio.create_task(
            processor.process(
                _item({"resource_id": "race-1", "version": 1}),
                _Lease(),
            )
        )
        assert await asyncio.to_thread(index.started.wait, 1)
        connection.set_current(_current_document(version=2))
        index.release.set()
        return await task, index.operations

    result, operations = asyncio.run(scenario())

    assert result.status == "succeeded"
    assert [operation[0] for operation in operations] == ["delete", "upsert"]
    assert operations[-1][1]["resource_version"] == 2
