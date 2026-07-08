import asyncio
from unittest.mock import MagicMock
from datetime import datetime, timezone

from data_foundation.processors.graph import GraphProcessor
from data_foundation.processors.base import PermanentProcessingError
from data_foundation.models import OutboxItem
from data_foundation.engine_config import FalkorConfig


def _item(payload):
    now = datetime.now(timezone.utc)
    return OutboxItem(id="i1", tenant_id="default", resource_id=payload.get("resource_id"),
        resource_version=payload.get("version"), topic="graph_ingest", dedupe_key="d",
        payload=payload, status="processing", attempts=1, next_attempt_at=now, lease_owner="w",
        lease_expires_at=now, error_code=None, error_summary=None, dead_at=None,
        created_at=now, updated_at=now)


class _Lease:
    async def assert_owned(self):
        return None


def test_state_disabled_without_config():
    p = GraphProcessor(conn=MagicMock(), graph=MagicMock(),
                       config=FalkorConfig(state="disabled", url="", graph_name="xhs"))
    assert p.state().status == "disabled"
    assert p.state().reason_code == "FALKOR_CONFIG_MISSING"


def test_process_merges_node_and_its_edges():
    # 处理器按查询开 dict_row cursor(不再改写共享连接的 row_factory),故 mock 走 cursor 路径。
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.return_value.fetchone.return_value = {
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record", "title": "T"}
    cur.execute.return_value.fetchall.return_value = [
        {"source_resource_id": "r1", "target_resource_id": "r2", "edge_type": "derived_from",
         "weight": 1.0, "properties": {}}]
    graph = MagicMock()
    p = GraphProcessor(conn=conn, graph=graph, config=FalkorConfig(state="enabled", url="u", graph_name="xhs"))
    result = asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert result.status == "succeeded"
    graph.merge_node.assert_called_once()
    graph.merge_edge.assert_called_once()
    assert graph.merge_edge.call_args.kwargs["edge_type"] == "derived_from"
    # 占位节点补 tenant 的前提:处理器必须把 outbox item 的 tenant 传给 merge_edge。
    assert graph.merge_edge.call_args.kwargs["tenant_id"] == "default"


def test_process_deletes_node_when_resource_gone():
    """资源已从核心库消失(查得 None):物理删除图节点及其边(DETACH DELETE),
    使图谱与核心库一致,而非仅标记 superseded 却把节点永久留在图里。"""
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.return_value.fetchone.return_value = None
    graph = MagicMock()
    p = GraphProcessor(conn=conn, graph=graph, config=FalkorConfig(state="enabled", url="u", graph_name="xhs"))
    result = asyncio.run(p.process(_item({"resource_id": "gone-1", "version": 2}), _Lease()))
    assert result.status == "superseded"
    graph.delete_node.assert_called_once_with("gone-1")
    graph.merge_node.assert_not_called()


def test_process_missing_resource_id_is_permanent():
    p = GraphProcessor(conn=MagicMock(), graph=MagicMock(),
                       config=FalkorConfig(state="enabled", url="u", graph_name="xhs"))
    try:
        asyncio.run(p.process(_item({"version": 1}), _Lease()))
        assert False, "should raise"
    except PermanentProcessingError:
        pass
