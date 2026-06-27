from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import tools.online_adopt as oa


class FakeRepo:
    """模拟 ResourceRepository 的 mapping 幂等 + 效果指标 + 边去重行为。"""

    def __init__(self):
        self.resources: dict[str, dict] = {}
        self.mappings: dict[tuple, str] = {}
        self.edges: dict[tuple, float] = {}
        self._metric_by_target: dict[str, str] = {}
        self._seq = 0

    def unit_of_work(self):
        return nullcontext()

    def _new_id(self, prefix):
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def upsert_resource(self, *, resource_type, title, mapping=None, resource_id=None,
                        content_json=None, **kwargs):
        rid = resource_id
        if mapping is not None:
            key = (mapping["system"], mapping["external_type"], mapping["external_id"])
            if key in self.mappings:
                rid = self.mappings[key]
        if rid is None:
            rid = self._new_id("res")
        self.resources[rid] = {"type": resource_type, "title": title, "content_json": content_json or {}}
        if mapping is not None:
            self.mappings[(mapping["system"], mapping["external_type"], mapping["external_id"])] = rid
        if resource_type == "performance_metric":
            target = (content_json or {}).get("target_resource_id")
            if target:
                self._metric_by_target[target] = rid
        return SimpleNamespace(id=rid, type=resource_type, title=title, version=1)

    def writable_resource_metadata(self, *, tenant_id, actor_open_id, resource_id, conn=None):
        return {"id": resource_id, "visibility": "team", "owner_open_id": actor_open_id}

    def find_performance_metric_id(self, *, tenant_id, target_resource_id, conn=None):
        return self._metric_by_target.get(target_resource_id)

    def add_edge(self, *, tenant_id, source_resource_id, target_resource_id, edge_type, weight=1.0):
        self.edges[(source_resource_id, target_resource_id, edge_type)] = weight

    def existing_mapping_external_ids(self, *, tenant_id, system, external_type, external_ids):
        return {
            eid for eid in external_ids
            if (system, external_type, eid) in self.mappings
        }

    def upsert_mapping(self, *, tenant_id, resource_id, system, external_type, external_id,
                       external_updated_at=None, sync_status="synced", conn=None):
        self.mappings[(system, external_type, external_id)] = resource_id


def _note(note_id="abc", **over):
    base = {
        "note_id": note_id,
        "note_url": f"http://xhslink.com/o/{note_id}",
        "title": "线上笔记",
        "summary": "摘要",
        "author": "博主",
        "likes": 3000, "collects": 1500, "comments": 300, "shares": 200,
        "created_at": "2026-06-20",
        "tags": ["护肤"],
    }
    base.update(over)
    return base


@pytest.fixture
def patched(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(oa, "connect", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(oa, "ResourceRepository", lambda conn: repo)
    monkeypatch.setattr(oa, "actor_from_config", lambda config: "ou_user")
    monkeypatch.setattr(oa, "default_tenant_id", lambda: "default")
    return repo


def test_adopt_requires_selected_notes(patched):
    """state 没有 selected_notes 时报错(前端必须直传)。"""
    assert oa.adopt_online_notes.func(selected_notes=[])["ok"] is False
    assert oa.adopt_online_notes.func(selected_notes=None)["ok"] is False


def test_adopt_data_only_from_state_not_llm():
    """完整修复:工具对 LLM 不暴露 notes 参数,数据唯一来自 state(InjectedState)。"""
    llm_args = list(oa.adopt_online_notes.args.keys())
    assert "notes" not in llm_args
    assert "selected_notes" not in llm_args  # InjectedState 对模型不可见


def test_real_repository_exposes_mapping_methods():
    """回归护栏:adopt/sync 依赖的真实 ResourceRepository mapping 方法必须存在。

    (历史 bug:编辑曾误删 _lock_mapping 签名,使 mapping-based upsert 在运行期才炸,
    单测因用 FakeRepo 未覆盖。此处对真类做结构断言,确保不再回归。)
    """
    from data_foundation.repositories.resource import ResourceRepository

    for name in (
        "_lock_mapping",
        "_resource_id_for_mapping",
        "_upsert_mapping",
        "upsert_mapping",
        "existing_mapping_external_ids",
    ):
        assert hasattr(ResourceRepository, name), f"ResourceRepository missing {name}"


def test_adopt_writes_db_metric_and_feishu(patched):
    repo = patched
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "rec_1"}) as mock_feishu:
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=True)
    assert res["ok"] is True
    r = res["results"][0]
    assert r["adopted"] is True
    assert r["feishu_synced"] is True
    assert res.get("next_step") and "选题" in res["next_step"]
    types = sorted(v["type"] for v in repo.resources.values())
    assert types == ["performance_metric", "xhs_online_note"]
    measured = [e for e in repo.edges if e[2] == "measured_by"]
    assert len(measured) == 1
    mock_feishu.assert_called_once()


def test_adopt_stores_full_authoritative_fields(patched):
    """state 直传的笔记原样落库(零转写):摘要/标签/互动数完整保留。"""
    repo = patched
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "rec_1"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note(note_id="abc")], sync_feishu=True)
    rid = res["results"][0]["resource_id"]
    stored = repo.resources[rid]["content_json"]
    assert stored["summary"] == "摘要"
    assert stored["tags"] == ["护肤"]
    assert stored["likes"] == 3000


def test_adopt_is_idempotent(patched):
    repo = patched
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "rec_1"}) as mock_feishu:
        oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=True)
        res2 = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=True)
    note_ids = [k for k, v in repo.resources.items() if v["type"] == "xhs_online_note"]
    metric_ids = [k for k, v in repo.resources.items() if v["type"] == "performance_metric"]
    assert len(note_ids) == 1
    assert len(metric_ids) == 1
    assert len([e for e in repo.edges if e[2] == "measured_by"]) == 1
    assert res2["results"][0]["feishu_synced"] == "skipped"
    assert mock_feishu.call_count == 1


def test_adopt_feishu_failure_keeps_db(patched):
    repo = patched
    with patch.object(oa, "create_online_note_record", return_value={"ok": False, "error": "perm denied"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=True)
    r = res["results"][0]
    assert r["adopted"] is True
    assert r["feishu_synced"] == "failed"
    assert any("FEISHU_SYNC_FAILED" in e["error"] for e in res["errors"])
    assert any(v["type"] == "xhs_online_note" for v in repo.resources.values())


def test_adopt_missing_note_id_collected_as_error(patched):
    res = oa.adopt_online_notes.func(selected_notes=[{"title": "无 id"}], sync_feishu=False)
    assert res["ok"] is True
    assert res["results"] == []
    assert res["errors"][0]["error"].startswith("DB_ADOPT_FAILED") or "note_id" in res["errors"][0]["error"]
