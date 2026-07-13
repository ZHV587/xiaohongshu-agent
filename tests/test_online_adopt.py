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
        self.edge_versions: dict[tuple, tuple[int, int]] = {}
        self.unreadable: set = set()  # 放进来的 resource_id 视为 actor 不可读(测越权闸门)

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
        self.resources[rid] = {
            "type": resource_type,
            "title": title,
            "content_json": content_json or {},
            "version": 1,
        }
        if mapping is not None:
            self.mappings[(mapping["system"], mapping["external_type"], mapping["external_id"])] = rid
        if resource_type == "performance_metric":
            target = (content_json or {}).get("target_resource_id")
            if target:
                self._metric_by_target[target] = rid
        return SimpleNamespace(id=rid, type=resource_type, title=title, version=1)

    def writable_resource_metadata(self, *, tenant_id, actor_open_id, resource_id, conn=None):
        resource = self.resources[resource_id]
        return {
            "id": resource_id,
            "type": resource["type"],
            "version": 1,
            "visibility": "team",
            "owner_open_id": actor_open_id,
        }

    def find_performance_metric_id(self, *, tenant_id, target_resource_id, conn=None):
        return self._metric_by_target.get(target_resource_id)

    def add_edge(
        self,
        *,
        tenant_id,
        source_resource_id,
        source_resource_version,
        target_resource_id,
        target_resource_version,
        edge_type,
        weight=1.0,
        properties=None,
    ):
        key = (source_resource_id, target_resource_id, edge_type)
        self.edges[key] = weight
        self.edge_versions[key] = (source_resource_version, target_resource_version)

    def existing_mapping_external_ids(self, *, tenant_id, system, external_type, external_ids):
        return {
            eid for eid in external_ids
            if (system, external_type, eid) in self.mappings
        }

    def upsert_mapping(self, *, tenant_id, resource_id, system, external_type, external_id,
                       external_updated_at=None, sync_status="synced", conn=None):
        self.mappings[(system, external_type, external_id)] = resource_id

    # associate_ingested_resource 会对每个候选 target 过读权限闸门(_actor_can_read)。
    # FakeRepo 默认全部可读,除非放进 unreadable 集合。
    conn = None

    def check_permission(self, resource_id, actor, permission="read", conn=None):
        if resource_id in self.unreadable:
            raise PermissionError("not readable")
        return True

    def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
        if resource_id in self.unreadable or resource_version <= 0:
            return None
        return SimpleNamespace(id=resource_id, version=resource_version)


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
    import data_foundation.preference_learning as preference_learning

    class _PreferenceRecorder:
        events = []

        def __init__(self, _repo):
            pass

        def record_exact_event(self, **kwargs):
            self.events.append(dict(kwargs))
            return {"ok": True, "inserted": True}

    repo = FakeRepo()
    monkeypatch.setattr(oa, "connect", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(oa, "ResourceRepository", lambda conn: repo)
    monkeypatch.setattr(oa, "actor_from_config", lambda config: "ou_user")
    monkeypatch.setattr(oa, "default_tenant_id", lambda: "default")
    monkeypatch.setattr(preference_learning, "PreferenceLearningService", _PreferenceRecorder)
    repo.preference_events = _PreferenceRecorder.events
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


def test_adopt_result_carries_title_and_new_vs_skipped(patched):
    """结果行回带 title,并区分「本次新收录」与「库里早有(跳过)」——供前端拆成/跳/败三态。"""
    repo = patched
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        # 首次:库里没有 → 新收录,already_adopted=False。
        first = oa.adopt_online_notes.func(
            selected_notes=[_note(note_id="abc", title="露营装备清单")], sync_feishu=False
        )
        r1 = first["results"][0]
        assert r1["title"] == "露营装备清单"
        assert r1["already_adopted"] is False
        # 再次采纳同一条:upsert 幂等,但对用户是「跳过」(库里早有)→ already_adopted=True。
        second = oa.adopt_online_notes.func(
            selected_notes=[_note(note_id="abc", title="露营装备清单")], sync_feishu=False
        )
        assert second["results"][0]["already_adopted"] is True
        # 全跳过时笔记仍在库、仍可据此出选题 → next_step 照常给出;但如实叙述「库里早有」,
        # 不把跳过项当新入库邀功(new_count=0 时括注只提跳过条数)。
        assert second.get("next_step") and "库里早有" in second["next_step"]


def test_adopt_result_title_falls_back_to_note_id(patched):
    """笔记无 title 时,结果行 title 兜底为 note_id(前端弹窗至少有可辨识文案,不空行)。"""
    repo = patched
    res = oa.adopt_online_notes.func(selected_notes=[_note(note_id="xyz", title="")], sync_feishu=False)
    assert res["results"][0]["title"] == "xyz"


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


# ── §0 素材不孤立:入库自动挂关联 ──────────────────────────────────────────────

def test_adopt_links_semantic_neighbors(patched, monkeypatch):
    """有已有素材时:采纳的笔记对语义/主题邻居建 semantically_related 边(权重=score)。"""
    repo = patched
    # 先塞一条"已有素材"当邻居(真实检索命中的库内资源)。
    monkeypatch.setattr(
        oa, "_find_neighbors",
        lambda repo, *, query, tenant_id, actor_open_id: [
            {"resource_id": "res-existing", "resource_version": 5, "score": 0.83}
        ],
    )
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=False)
    rid = res["results"][0]["resource_id"]
    sem = [e for e in repo.edges if e[2] == "semantically_related"]
    assert (rid, "res-existing", "semantically_related") in repo.edges
    assert repo.edges[(rid, "res-existing", "semantically_related")] == pytest.approx(0.83)
    assert len(sem) == 1
    assert res["results"][0]["associations"] == {"semantic": 1, "co_ingested": 0, "isolated": False}


def test_adopt_batch_co_ingested_fallback(patched, monkeypatch):
    """无语义邻居(空库)但同批多条:退化为 co_ingested 互挂,保证不孤岛。"""
    repo = patched
    monkeypatch.setattr(
        oa,
        "_find_neighbors",
        lambda repo, *, query, tenant_id, actor_open_id: [],
    )
    notes = [_note(note_id="a"), _note(note_id="b")]
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        res = oa.adopt_online_notes.func(selected_notes=notes, sync_feishu=False)
    co = [e for e in repo.edges if e[2] == "co_ingested"]
    # 两条各挂到对方 → 2 条 co_ingested 边,均非孤岛。
    assert len(co) == 2
    for r in res["results"]:
        assert r["associations"]["co_ingested"] >= 1
        assert r["associations"]["isolated"] is False


def test_adopt_single_note_empty_library_is_isolated(patched, monkeypatch):
    """全库第一条素材(无邻居、无同批伙伴):唯一允许无边的情形,如实标 isolated。"""
    repo = patched
    monkeypatch.setattr(
        oa,
        "_find_neighbors",
        lambda repo, *, query, tenant_id, actor_open_id: [],
    )
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=False)
    assert not [e for e in repo.edges if e[2] in ("semantically_related", "co_ingested")]
    assert res["results"][0]["associations"]["isolated"] is True


def test_adopt_skips_unreadable_neighbor(patched, monkeypatch):
    """越权闸门:邻居 target 对 actor 不可读时不建边(防连到他人私有资源)。"""
    repo = patched
    repo.unreadable.add("res-private")
    monkeypatch.setattr(
        oa, "_find_neighbors",
        lambda repo, *, query, tenant_id, actor_open_id: [
            {"resource_id": "res-private", "resource_version": 2, "score": 0.9}
        ],
    )
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=False)
    assert not [e for e in repo.edges if e[2] == "semantically_related"]
    # 单条 + 邻居不可读 + 无同批伙伴 → 孤岛(如实标记,不硬连不可读资源)。
    assert res["results"][0]["associations"]["isolated"] is True


def test_adopt_association_failure_does_not_break_adopt(patched, monkeypatch):
    """关联建边报错绝不影响采纳:采纳仍成功,错误进 errors。"""
    repo = patched

    def boom(repo, *, query, tenant_id, actor_open_id):
        raise RuntimeError("neighbor search exploded")

    monkeypatch.setattr(oa, "_find_neighbors", boom)
    with patch.object(oa, "create_online_note_record", return_value={"ok": True, "record_id": "r"}):
        res = oa.adopt_online_notes.func(selected_notes=[_note()], sync_feishu=False)
    assert res["ok"] is True
    assert res["results"][0]["adopted"] is True
    assert any("ASSOCIATION_FAILED" in e["error"] for e in res["errors"])
