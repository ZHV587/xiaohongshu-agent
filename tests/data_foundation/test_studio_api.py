from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from tests.data_foundation.asgi_client import ASGIClient


def _client(monkeypatch, *, secret: str = "internal-secret", admins: str = "ou_admin"):
    monkeypatch.setenv("XHS_INTERNAL_SECRET", secret)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", admins)
    import data_foundation.http_app as http_app

    return ASGIClient(http_app.app)


def _user_headers(open_id: str = "ou_user", is_admin: str = "false") -> dict[str, str]:
    return {
        "X-XHS-Internal-Key": "internal-secret",
        "X-XHS-Open-Id": open_id,
        "X-XHS-Is-Admin": is_admin,
    }


def _admin_headers(open_id: str = "ou_admin") -> dict[str, str]:
    return {
        "X-XHS-Internal-Key": "internal-secret",
        "X-XHS-Open-Id": open_id,
        "X-XHS-Is-Admin": "true",
    }


# ── 鉴权(需求 17.1/17.2/17.3) ──


def test_studio_endpoints_reject_missing_internal_key(monkeypatch):
    client = _client(monkeypatch)
    for path in (
        "/internal/studio/analytics",
        "/internal/studio/calendar",
        "/internal/studio/accounts",
        "/internal/studio/pipeline",
        "/internal/studio/recents",
        "/internal/studio/trends",
    ):
        response = client.get(path)
        assert response.status_code == 401, path
        # 响应体不含业务字段或令牌
        body = response.json()
        assert "dashboard" not in body and "accounts" not in body and "queue" not in body


def test_analytics_matrix_overview_requires_admin(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")
    # 无 account(矩阵总览,跨账号聚合)→ 普通用户被拒(需求 17.1)
    response = client.get("/internal/studio/analytics", headers=_user_headers())
    assert response.status_code == 403


def test_matrix_overview_endpoints_require_admin(monkeypatch):
    # calendar/pipeline 矩阵总览(无 account)与 accounts 均跨 owner 聚合,普通用户须被拒 403。
    # 底层聚合不带 owner 过滤,无 account 即全租户可见——杜绝越权读他人排期/发布管线(需求 17.1)。
    client = _client(monkeypatch, admins="ou_admin")
    for path in ("/internal/studio/calendar", "/internal/studio/pipeline", "/internal/studio/accounts"):
        response = client.get(path, headers=_user_headers())
        assert response.status_code == 403, path
    # 指定 account 的单账号视图仍允许普通用户(calendar/pipeline)
    import data_foundation.operations as operations
    import data_foundation.studio_api as studio_api

    monkeypatch.setattr(operations, "_load_schedule_items", lambda *, tenant_id, account: [])
    monkeypatch.setattr(studio_api, "load_pipeline", lambda *, tenant_id, account: [])
    for path in ("/internal/studio/calendar?account=acc_1", "/internal/studio/pipeline?account=acc_1"):
        response = client.get(path, headers=_user_headers())
        assert response.status_code == 200, path


def test_analytics_account_view_allows_user(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")
    import data_foundation.studio_api as studio_api

    monkeypatch.setattr(
        studio_api,
        "load_analytics",
        lambda *, tenant_id, account: {
            "dashboard": [],
            "library": [],
            "teardown": {"title": "", "points": []},
        },
    )
    response = client.get("/internal/studio/analytics?account=acc_1", headers=_user_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["account"] == "acc_1"
    # 单账号视图无真实归属 → 真实空集合(需求 10.4/11.4)
    assert payload["dashboard"] == []
    assert payload["library"] == []
    assert payload["teardown"] == {"title": "", "points": []}


def test_calendar_contract_shape_and_empty_grid(monkeypatch):
    # 存储可用但无排期行 → 200 + 真实月份网格 + 空 calendar(需求 12.4)。
    # _load_schedule_items 走真实 DB;此处注入空排期模拟「库里暂无排期」,与「库不可用」区分。
    import data_foundation.operations as operations

    monkeypatch.setattr(operations, "_load_schedule_items", lambda *, tenant_id, account: [])
    client = _client(monkeypatch)
    # 无 account = 矩阵总览 → require_admin(需求 17.1)
    response = client.get("/internal/studio/calendar", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    month = payload["month"]
    assert set(month) == {"label", "days", "firstOffset"}
    assert 28 <= month["days"] <= 31
    assert 0 <= month["firstOffset"] <= 6
    assert payload["calendar"] == []


def test_calendar_store_unavailable_returns_503_not_degraded(monkeypatch):
    # 排期存储不可用是真实错误 → 503(不降级吞成 200+空网格;严禁兼容兜底)。
    import data_foundation.operations as operations

    def _boom(*, tenant_id, account):
        raise RuntimeError("postgresql://user:db-secret@host/db down")

    monkeypatch.setattr(operations, "_load_schedule_items", _boom)
    client = _client(monkeypatch)
    response = client.get("/internal/studio/calendar", headers=_admin_headers())
    assert response.status_code == 503
    assert "db-secret" not in response.text  # 不回带异常细节


def test_accounts_empty_overview_all_zero(monkeypatch):
    client = _client(monkeypatch)
    # 账号矩阵总览 → require_admin(需求 17.1)
    response = client.get("/internal/studio/accounts", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.json()
    # 无账号实体模型 → 真实空集合 + overview 全 0(需求 9.5)
    assert payload["accounts"] == []
    assert payload["overview"] == {
        "totalFans": 0,
        "weekNewFans": 0,
        "weekPosts": 0,
        "avgHotRate": 0,
    }


def test_trends_empty_without_real_source(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/internal/studio/trends", headers=_user_headers())
    assert response.status_code == 200
    assert response.json()["trends"] == []


def test_recents_forwards_open_id_and_orders(monkeypatch):
    client = _client(monkeypatch)
    import data_foundation.studio_api as studio_api

    captured = {}

    def _fake_recents(*, tenant_id, open_id):
        captured["open_id"] = open_id
        return [
            {"id": 1, "icon": "📝", "title": "新稿", "status": "draft"},
            {"id": 2, "icon": "💡", "title": "旧选题", "status": "synced"},
        ]

    monkeypatch.setattr(studio_api, "load_recents", _fake_recents)
    response = client.get("/internal/studio/recents", headers=_user_headers(open_id="ou_alice"))
    assert response.status_code == 200
    assert captured["open_id"] == "ou_alice"
    recents = response.json()["recents"]
    assert [r["id"] for r in recents] == [1, 2]


def test_aggregation_error_returns_503_without_leak(monkeypatch):
    client = _client(monkeypatch)
    import data_foundation.studio_api as studio_api

    def _boom(*, tenant_id, open_id):
        raise RuntimeError("postgresql://user:db-secret@host/db")

    monkeypatch.setattr(studio_api, "load_recents", _boom)
    response = client.get("/internal/studio/recents", headers=_user_headers())
    assert response.status_code == 503
    assert "db-secret" not in response.text


# ── 纯聚合逻辑(无 DB) ──


def test_build_dashboard_skips_zero_and_computes_real_delta():
    from data_foundation.operations import _build_dashboard

    now = datetime.now(timezone.utc)
    rows = [
        {"content_json": {"metrics": {"likes": 100, "views": 0}}, "updated_at": now - timedelta(days=1)},
        {"content_json": {"metrics": {"likes": 40}}, "updated_at": now - timedelta(days=10)},
    ]
    cards = _build_dashboard(rows)
    labels = {c["label"]: c for c in cards}
    # likes 有真实总量 → 出卡;views 全 0 → 不出卡(不补 0 值占位)
    assert "总点赞" in labels
    assert "总曝光" not in labels
    likes = labels["总点赞"]
    assert likes["value"] == "140"
    # 本周 100 vs 上周 40 → delta = round((100-40)/40*100) = 150
    assert likes["delta"] == 150
    assert likes["tone"] == "coral"


def test_build_library_normalizes_hot_and_teardown_top():
    from data_foundation.operations import _build_library_and_teardown

    rows = [
        {
            "id": "a",
            "title": "高分稿",
            "summary": "s1",
            "copy_json": {"source_topic": "露营"},
            "copy_updated": None,
            "metric_json": {"score": 0.9, "metrics": {"likes": 12000, "collects": 3400}, "note_url": "u"},
        },
        {
            "id": "b",
            "title": "低分稿",
            "summary": "s2",
            "copy_json": {},
            "copy_updated": None,
            "metric_json": {"score": 0.1, "metrics": {"likes": 10}, "note_url": "u"},
        },
        {
            "id": "c",
            "title": "未回填稿",
            "summary": "s3",
            "copy_json": {},
            "copy_updated": None,
            "metric_json": None,
        },
    ]
    library, teardown = _build_library_and_teardown(rows)
    assert len(library) == 3
    by_title = {it["title"]: it for it in library}
    # 已回填条目按真实 score 归一到 1–100;最高分 → 100,最低分 → 1
    assert by_title["高分稿"]["hot"] == 100
    assert by_title["低分稿"]["hot"] == 1
    # 未回填 → hot=0(真实「暂无效果数据」哨兵),状态草稿
    assert by_title["未回填稿"]["hot"] == 0
    assert by_title["未回填稿"]["status"] == "草稿"
    assert by_title["高分稿"]["likes"] == "1.2万"
    # 拆解取最高分已回填稿标题;points 无真实拆解分析 → []
    assert teardown["title"] == "高分稿"
    assert teardown["points"] == []


def test_compact_number_chinese_units():
    from data_foundation.operations import _compact_number

    assert _compact_number(0) == "0"
    assert _compact_number(999) == "999"
    assert _compact_number(12400) == "1.2万"
    assert _compact_number(52000) == "5.2万"
    assert _compact_number(120000000) == "1.2亿"


# ── 写接口:鉴权与契约(handler 层,monkeypatch 落库 helper,不依赖 DB) ──


def _patch_persist(monkeypatch, name, fn):
    """替换 studio_api 的落库 helper(handler 契约/鉴权测试用,隔离 DB)。"""
    import data_foundation.studio_api as studio_api

    monkeypatch.setattr(studio_api, name, fn)


def test_write_endpoints_reject_missing_internal_key(monkeypatch):
    client = _client(monkeypatch)
    # 排期/回填/推进 stage 三个写端点未带内部密钥一律 401,且响应体不含业务字段
    for path, body in (
        ("/internal/studio/schedule", {"resourceId": "11111111-1111-1111-1111-111111111111", "date": "2026-02-12", "time": "19:00", "account": "a"}),
        ("/internal/studio/backfill", {"resourceId": "11111111-1111-1111-1111-111111111111", "metrics": {"likes": 1}}),
        ("/internal/studio/pipeline-advance", {"resourceId": "11111111-1111-1111-1111-111111111111", "toStage": "measured"}),
    ):
        response = client.post(path, json=body)
        assert response.status_code == 401, path
        assert "scheduled" not in response.json()


def test_schedule_missing_field_returns_400(monkeypatch):
    client = _client(monkeypatch)
    base = {"resourceId": "11111111-1111-1111-1111-111111111111", "targetResourceVersion": 1, "expectedLatestResourceVersion": 1, "expectedStateVersion": 1, "date": "2026-02-12", "time": "19:00", "account": "acc_1"}
    for field in ("resourceId", "targetResourceVersion", "expectedLatestResourceVersion", "expectedStateVersion", "date", "time", "account"):
        body = dict(base)
        body.pop(field)
        response = client.post("/internal/studio/schedule", headers=_user_headers(), json=body)
        assert response.status_code == 400, field
        assert field in response.json()["error"]


def test_schedule_success_returns_scheduled_item(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def _fake(*, tenant_id, actor_open_id, resource_id, target_resource_version, expected_latest_resource_version, expected_state_version, date, time, account, final_draft=None, request_id=None):
        captured.update(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id,
            date=date, time=time, account=account,
        )
        return {"date": 12, "item": {"t": "露营避坑", "time": time, "tone": "coral", "acct": account}, "resourceVersion": target_resource_version, "stateVersion": 2}

    _patch_persist(monkeypatch, "_persist_schedule", _fake)
    response = client.post(
        "/internal/studio/schedule",
        headers=_user_headers(open_id="ou_alice"),
        json={"resourceId": " 11111111-1111-1111-1111-111111111111 ", "targetResourceVersion": 1, "expectedLatestResourceVersion": 1, "expectedStateVersion": 1, "date": "2026-02-12", "time": "19:00", "account": "acc_1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["scheduled"] == {
        "date": 12,
        "item": {"t": "露营避坑", "time": "19:00", "tone": "coral", "acct": "acc_1"},
        "resourceVersion": 1,
        "stateVersion": 2,
    }
    # handler 转发前 strip,落库收到去空白后的 resourceId 与登录身份
    assert captured["resource_id"] == "11111111-1111-1111-1111-111111111111"
    assert captured["actor_open_id"] == "ou_alice"


def test_schedule_final_draft_requires_and_forwards_stable_request_id(monkeypatch):
    client = _client(monkeypatch)
    body = {
        "resourceId": "11111111-1111-1111-1111-111111111111",
        "targetResourceVersion": 1,
        "expectedLatestResourceVersion": 1,
        "expectedStateVersion": 1,
        "date": "2026-02-12",
        "time": "19:00",
        "account": "acc_1",
        "finalDraft": {"title": "Final", "body": "Body", "tags": []},
    }
    missing = client.post(
        "/internal/studio/schedule", headers=_user_headers(), json=body
    )
    assert missing.status_code == 400
    assert "requestId" in missing.json()["error"]

    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return {
            "date": 12,
            "item": {"t": "Final", "time": "19:00", "tone": "coral", "acct": "acc_1"},
            "resourceVersion": 2,
            "stateVersion": 2,
        }

    _patch_persist(monkeypatch, "_persist_schedule", _fake)
    body["requestId"] = "stable-schedule-attempt-1"
    response = client.post(
        "/internal/studio/schedule", headers=_user_headers(), json=body
    )
    assert response.status_code == 200
    assert captured["request_id"] == "stable-schedule-attempt-1"
    assert captured["final_draft"] == body["finalDraft"]


def test_schedule_persist_failure_returns_500_without_leak(monkeypatch):
    client = _client(monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("postgresql://user:db-secret@host/db")

    _patch_persist(monkeypatch, "_persist_schedule", _boom)
    response = client.post(
        "/internal/studio/schedule",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "targetResourceVersion": 1, "expectedLatestResourceVersion": 1, "expectedStateVersion": 1, "date": "2026-02-12", "time": "19:00", "account": "acc_1"},
    )
    # 落库失败整体失败(前端据此回滚乐观更新),不回带异常细节
    assert response.status_code == 500
    assert "db-secret" not in response.text


def test_backfill_missing_resource_id_returns_400(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/internal/studio/backfill", headers=_user_headers(), json={"metrics": {"likes": 1}}
    )
    assert response.status_code == 400
    assert "resourceId" in response.json()["error"]


def test_backfill_missing_metrics_returns_400(monkeypatch):
    client = _client(monkeypatch)
    for metrics in (None, "x", [1, 2]):
        body = {"resourceId": "11111111-1111-1111-1111-111111111111"}
        if metrics is not None:
            body["metrics"] = metrics
        response = client.post("/internal/studio/backfill", headers=_user_headers(), json=body)
        assert response.status_code == 400, metrics
        assert "metrics" in response.json()["error"]


def test_backfill_invalid_metrics_returns_400(monkeypatch):
    client = _client(monkeypatch)

    def _raise(**kwargs):
        # 模拟 _clean_metrics 对非数值/负值抛 ValueError(需求 15.3)
        raise ValueError("metrics must be non-negative")

    _patch_persist(monkeypatch, "_persist_backfill", _raise)
    response = client.post(
        "/internal/studio/backfill",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "metrics": {"likes": -3}},
    )
    assert response.status_code == 400
    assert "non-negative" in response.json()["error"]


def test_write_endpoints_reject_malformed_resource_id_returns_400(monkeypatch):
    # resourceId 是数据底座 uuid 列:格式非法(非 uuid)应在 handler 边界判 400,
    # 而非把 Postgres uuid 转换错误冒成 500(端到端基线发现的真实缺陷)。
    client = _client(monkeypatch)
    cases = (
        ("/internal/studio/backfill", {"resourceId": "not-a-uuid", "metrics": {"likes": 1}}),
        ("/internal/studio/schedule", {"resourceId": "not-a-uuid", "targetResourceVersion": 1, "expectedLatestResourceVersion": 1, "expectedStateVersion": 1, "date": "2026-02-12", "time": "19:00", "account": "acc_1"}),
        ("/internal/studio/pipeline-advance", {"resourceId": "not-a-uuid", "toStage": "measured"}),
    )
    for path, body in cases:
        response = client.post(path, headers=_user_headers(), json=body)
        assert response.status_code == 400, path
        assert "uuid" in response.json()["error"].lower(), path


def test_backfill_success_returns_score(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def _fake(*, tenant_id, actor_open_id, resource_id, metrics, published_at=None, note_url=None, target_resource_version=None):
        captured.update(resource_id=resource_id, metrics=metrics, note_url=note_url)
        return {"score": 0.42, "target_resource_version": 3}

    _patch_persist(monkeypatch, "_persist_backfill", _fake)
    response = client.post(
        "/internal/studio/backfill",
        headers=_user_headers(),
        json={
            "resourceId": "11111111-1111-1111-1111-111111111111",
            "metrics": {"views": 12000, "likes": 1240, "collects": 340},
            "link": "https://xhslink/abc",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"ok": True, "score": 0.42, "resourceVersion": 3}
    assert captured["metrics"] == {"views": 12000, "likes": 1240, "collects": 340}
    assert captured["note_url"] == "https://xhslink/abc"


def test_pipeline_advance_missing_field_returns_400(monkeypatch):
    client = _client(monkeypatch)
    for body in ({"toStage": "measured"}, {"resourceId": "11111111-1111-1111-1111-111111111111"}):
        response = client.post("/internal/studio/pipeline-advance", headers=_user_headers(), json=body)
        assert response.status_code == 400


def test_pipeline_advance_invalid_stage_returns_400(monkeypatch):
    client = _client(monkeypatch)
    # toStage 仅允许 published/measured;scheduled 等逆向起点直接 400
    response = client.post(
        "/internal/studio/pipeline-advance",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "toStage": "scheduled"},
    )
    assert response.status_code == 400
    assert "toStage" in response.json()["error"]


def test_pipeline_advance_published_requires_link(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/internal/studio/pipeline-advance",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "toStage": "published"},
    )
    assert response.status_code == 400
    assert "link" in response.json()["error"]


def test_pipeline_advance_stage_conflict_returns_409(monkeypatch):
    client = _client(monkeypatch)
    import data_foundation.studio_api as studio_api

    def _conflict(**kwargs):
        raise studio_api._StageConflict("cannot advance from 'measured' to 'published'")

    _patch_persist(monkeypatch, "_persist_pipeline_stage", _conflict)
    response = client.post(
        "/internal/studio/pipeline-advance",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "toStage": "published", "link": "https://xhslink/abc"},
    )
    # 逆向/跨级/无起点 → 409(单向状态机,需求 13.3/13.4)
    assert response.status_code == 409
    assert "cannot advance" in response.json()["error"]


def test_pipeline_advance_success_returns_stage(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    def _fake(*, tenant_id, actor_open_id, resource_id, to_stage, link=None):
        captured.update(resource_id=resource_id, to_stage=to_stage, link=link)
        return {"stage": to_stage}

    _patch_persist(monkeypatch, "_persist_pipeline_stage", _fake)
    response = client.post(
        "/internal/studio/pipeline-advance",
        headers=_user_headers(),
        json={"resourceId": "11111111-1111-1111-1111-111111111111", "toStage": "published", "link": "https://xhslink/abc"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "stage": "published"}
    assert captured == {"resource_id": "11111111-1111-1111-1111-111111111111", "to_stage": "published", "link": "https://xhslink/abc"}


def test_copy_lifecycle_select_returns_exact_version_and_state_token(monkeypatch):
    from types import SimpleNamespace
    import data_foundation.studio_api as studio_api

    client = _client(monkeypatch)

    @contextmanager
    def _repo():
        yield object()

    class _Lifecycle:
        def __init__(self, _repo):
            pass

        def select_version(self, **kwargs):
            assert kwargs["resource_version"] == 2
            assert kwargs["expected_state_version"] == 3
            return SimpleNamespace(
                resource_id=kwargs["resource_id"], lifecycle_status="selected",
                selected_version=2, selected_label="B", adopted_version=None,
                finalized_version=None, published_version=None,
                knowledge_target_version=None, latest_resource_version=3, state_version=4,
            )

        def list_versions(self, **_kwargs):
            return [
                {
                    "resourceVersion": 2,
                    "label": "B",
                    "title": "B title",
                    "body": "B body",
                    "tags": [],
                    "cover": "",
                    "note": "",
                }
            ]

    monkeypatch.setattr(studio_api, "_repository", _repo)
    monkeypatch.setattr(studio_api, "GeneratedCopyRepository", _Lifecycle)
    response = client.post(
        "/internal/studio/copies/select",
        headers=_user_headers(),
        json={
            "resourceId": "11111111-1111-1111-1111-111111111111",
            "resourceVersion": 2,
            "expectedStateVersion": 3,
            "label": "B",
        },
    )
    assert response.status_code == 200
    assert response.json()["lifecycle"] == {
        "resourceId": "11111111-1111-1111-1111-111111111111",
        "status": "selected",
        "selectedVersion": 2,
        "selectedLabel": "B",
        "adoptedVersion": None,
        "finalizedVersion": None,
        "publishedVersion": None,
        "knowledgeTargetVersion": None,
        "latestResourceVersion": 3,
        "stateVersion": 4,
        "versions": [
            {
                "resourceVersion": 2,
                "label": "B",
                "title": "B title",
                "body": "B body",
                "tags": [],
                "cover": "",
                "note": "",
            }
        ],
    }


def test_copy_lifecycle_stale_write_returns_409(monkeypatch):
    import data_foundation.studio_api as studio_api

    client = _client(monkeypatch)

    @contextmanager
    def _repo():
        yield object()

    class _Lifecycle:
        def __init__(self, _repo):
            pass

        def adopt_version(self, **_kwargs):
            raise studio_api.GeneratedCopyConflict("state version changed")

    monkeypatch.setattr(studio_api, "_repository", _repo)
    monkeypatch.setattr(studio_api, "GeneratedCopyRepository", _Lifecycle)
    response = client.post(
        "/internal/studio/copies/adopt",
        headers=_user_headers(),
        json={
            "resourceId": "11111111-1111-1111-1111-111111111111",
            "resourceVersion": 2,
            "expectedStateVersion": 1,
        },
    )
    assert response.status_code == 409
    assert "state version changed" in response.json()["error"]


# ── 写路径落库逻辑(fake 仓储跑真实代码路径,无 DB);断言写入的 content_json/边 ──
# ── 与 Epic 5 GET 的读取口径(_load_schedule_items / _load_pipeline)逐字段对齐(读写自洽)──


class _FakeResource:
    def __init__(
        self,
        rid,
        *,
        title="未命名笔记",
        content_text="正文",
        content_json=None,
        resource_type="performance_metric",
        version=1,
        visibility="team",
        owner_open_id="ou_user",
    ):
        self.id = rid
        self.title = title
        self.content_text = content_text
        self.content_json = dict(content_json or {})
        self.type = resource_type
        self.version = version
        self.visibility = visibility
        self.owner_open_id = owner_open_id


class _MemoryPreferenceRepository:
    """Studio tests exercise the real preference service without opening a database."""

    def __init__(self):
        self._observations = {}
        self._states = {}
        self.actor_locks = []

    def acquire_actor_lock(self, **kwargs):
        self.actor_locks.append((kwargs["tenant_id"], kwargs["actor_open_id"]))

    def insert_observation(self, *, tenant_id, actor_open_id, observation):
        key = (tenant_id, actor_open_id, observation.event_key)
        inserted = key not in self._observations
        self._observations.setdefault(key, observation)
        return inserted

    def list_observations(self, *, tenant_id, actor_open_id):
        return [
            observation
            for (tenant, actor, _), observation in self._observations.items()
            if tenant == tenant_id and actor == actor_open_id
        ]

    def get_profile_state(self, *, tenant_id, actor_open_id):
        return self._states.get((tenant_id, actor_open_id))

    def upsert_profile_state(self, *, tenant_id, actor_open_id, **state):
        key = (tenant_id, actor_open_id)
        previous = self._states.get(key)
        revision = 1 if previous is None else previous["revision"]
        if previous is not None and previous["input_digest"] != state["input_digest"]:
            revision += 1
        stored = {
            "tenant_id": tenant_id,
            "owner_open_id": actor_open_id,
            **state,
            "revision": revision,
        }
        self._states[key] = stored
        return stored


class _FakeRepo:
    """跑通 _persist_* 真实代码路径的内存仓储(对齐 ResourceRepository 被调用面)。"""

    def __init__(self, *, resources=None, metric_id=None, metric_content=None):
        self.conn = None
        self._resources = dict(resources or {})
        self._versions = {
            (resource_id, resource.version): resource
            for resource_id, resource in self._resources.items()
        }
        self._metric_id = metric_id
        if metric_id is not None:
            resource = self._resources.setdefault(
                metric_id, _FakeResource(metric_id, content_json=dict(metric_content or {}))
            )
            self._versions.setdefault((metric_id, resource.version), resource)
        self.upserts: list[dict] = []
        self.edges: list[dict] = []

    def unit_of_work(self):
        from contextlib import nullcontext

        return nullcontext()

    def get_resource(self, tenant_id, actor_open_id, resource_id):
        return self._resources.get(resource_id)

    def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
        return self._versions.get((resource_id, resource_version))

    def writable_resource_metadata(self, *, tenant_id, actor_open_id, resource_id):
        resource = self._resources[resource_id]
        return {
            "type": resource.type,
            "version": resource.version,
            "visibility": resource.visibility,
            "owner_open_id": resource.owner_open_id,
        }

    def resource_version_exists(self, *, tenant_id, resource_id, resource_version):
        return (resource_id, resource_version) in self._versions

    def find_performance_metric_id(self, *, tenant_id, target_resource_id):
        return self._metric_id

    def upsert_resource(self, **kwargs):
        rid = kwargs.get("resource_id") or f"metric-{len(self.upserts) + 1}"
        self.upserts.append(kwargs)
        # 回写内存,使后续 _existing_metric_content 读到刚写入的 content_json(回填二次合并依赖)
        previous = self._resources.get(rid)
        version = 1 if previous is None else previous.version + 1
        resource = _FakeResource(
            rid,
            title=kwargs.get("title", ""),
            content_text=kwargs.get("content_text") or "",
            content_json=dict(kwargs.get("content_json") or {}),
            resource_type=kwargs["resource_type"],
            version=version,
            visibility=kwargs["visibility"],
            owner_open_id=kwargs["owner_open_id"],
        )
        self._resources[rid] = resource
        self._versions[(rid, version)] = resource
        return resource

    def add_edge(self, **kwargs):
        self.edges.append(kwargs)


def _use_fake_repo(monkeypatch, repo):
    import data_foundation.studio_api as studio_api
    import data_foundation.repositories.preference as preference_repository

    @contextmanager
    def _fake_repository():
        yield repo

    monkeypatch.setattr(studio_api, "_repository", _fake_repository)
    class _FakeLifecycle:
        def __init__(self, resource_repo):
            self.resource_repo = resource_repo

        def finalize_for_schedule(self, **kwargs):
            return type("State", (), {
                "finalized_version": kwargs["target_resource_version"],
                "state_version": kwargs["expected_state_version"] + 1,
            })()

        def mark_published(self, **kwargs):
            return None

    monkeypatch.setattr(studio_api, "GeneratedCopyRepository", _FakeLifecycle)
    preference_memory = _MemoryPreferenceRepository()
    monkeypatch.setattr(
        preference_repository,
        "PreferenceRepository",
        lambda _conn: preference_memory,
    )
    repo.preference_memory = preference_memory
    monkeypatch.setattr(studio_api, "_best_effort_feishu_draft", lambda *a, **k: None)
    monkeypatch.setattr(studio_api, "_best_effort_feishu_metrics", lambda *a, **k: None)


def test_persist_schedule_writes_scheduled_metric_and_edge(monkeypatch):
    from data_foundation.studio_api import _persist_schedule

    repo = _FakeRepo(resources={"res_1": _FakeResource("res_1", title="露营避坑")})
    _use_fake_repo(monkeypatch, repo)
    result = _persist_schedule(
        tenant_id="default", actor_open_id="ou_user", resource_id="res_1",
        target_resource_version=1, expected_latest_resource_version=1,
        expected_state_version=1,
        date="2026-02-12", time="19:00", account="acc_1",
    )
    # 返回 calendar 排期项(日历 GET 按 day 分组渲染)
    assert result == {"date": 12, "item": {"t": "露营避坑", "time": "19:00", "tone": "coral", "acct": "acc_1"}, "resourceVersion": 1, "stateVersion": 2}
    content = repo.upserts[0]["content_json"]
    # 与 _load_schedule_items 读取口径对齐:scheduled_date/scheduled_time/account/stage
    assert content["scheduled_date"] == "2026-02-12"
    assert content["scheduled_time"] == "19:00"
    assert content["account"] == "acc_1"
    assert content["stage"] == "scheduled"
    assert content["target_resource_id"] == "res_1"
    assert content["target_resource_version"] == 1
    assert repo.upserts[0]["resource_type"] == "performance_metric"
    # measured_by 边:source=源 generated_copy,target=排期 performance_metric(GET 经此边回读标题)
    edge = repo.edges[0]
    assert edge["source_resource_id"] == "res_1"
    assert edge["edge_type"] == "measured_by"


def test_persist_schedule_not_downgrade_published_stage(monkeypatch):
    from data_foundation.studio_api import _persist_schedule

    repo = _FakeRepo(
        resources={"res_1": _FakeResource("res_1", title="已发布稿")},
        metric_id="m1",
        metric_content={"stage": "published", "note_url": "https://xhslink/x", "account": "acc_1"},
    )
    _use_fake_repo(monkeypatch, repo)
    _persist_schedule(
        tenant_id="default", actor_open_id="ou_user", resource_id="res_1",
        target_resource_version=1, expected_latest_resource_version=1,
        expected_state_version=1,
        date="2026-03-01", time="20:00", account="acc_1",
    )
    content = repo.upserts[0]["content_json"]
    # 已进入 published 的条目重排期只刷新排期元数据,不回退 stage(单向状态机)
    assert content["stage"] == "published"
    assert content["scheduled_date"] == "2026-03-01"


def test_schedule_and_feishu_use_finalized_snapshot_not_latest_candidate(monkeypatch):
    from data_foundation.studio_api import _persist_schedule
    import data_foundation.studio_api as studio_api

    latest = _FakeResource("res_1", title="C 未采纳标题", content_text="C 未采纳正文")
    finalized = _FakeResource("res_1", title="A 定稿标题", content_text="A 定稿正文")
    repo = _FakeRepo(resources={"res_1": latest})
    repo.get_resource_version = lambda tenant_id, actor_open_id, resource_id, resource_version: finalized
    _use_fake_repo(monkeypatch, repo)
    synced = {}
    monkeypatch.setattr(
        studio_api,
        "_best_effort_feishu_draft",
        lambda actor_open_id, **kwargs: synced.update(kwargs),
    )

    result = _persist_schedule(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="res_1",
        target_resource_version=1,
        expected_latest_resource_version=1,
        expected_state_version=1,
        date="2026-02-12",
        time="19:00",
        account="acc_1",
    )

    assert result["item"]["t"] == "A 定稿标题"
    assert repo.upserts[0]["title"].endswith("A 定稿标题")
    assert synced == {"title": "A 定稿标题", "content": "A 定稿正文"}


def test_persist_pipeline_stage_allows_forward_transitions(monkeypatch):
    from data_foundation.studio_api import _persist_pipeline_stage

    # scheduled → published:持久化 link
    repo = _FakeRepo(
        resources={"res_1": _FakeResource("res_1", title="待发布稿")},
        metric_id="m1",
        metric_content={"stage": "scheduled", "account": "acc_1", "target_resource_version": 1},
    )
    _use_fake_repo(monkeypatch, repo)
    result = _persist_pipeline_stage(
        tenant_id="default", actor_open_id="ou_user", resource_id="res_1",
        to_stage="published", link="https://xhslink/abc",
    )
    assert result == {"stage": "published"}
    content = repo.upserts[0]["content_json"]
    assert content["stage"] == "published"
    assert content["note_url"] == "https://xhslink/abc"
    assert content["published_at"]  # 自动补发布时间戳

    # published → measured
    repo2 = _FakeRepo(
        resources={"res_2": _FakeResource("res_2", title="已发布稿")},
        metric_id="m2",
        metric_content={"stage": "published", "note_url": "https://xhslink/keep", "target_resource_version": 1},
    )
    _use_fake_repo(monkeypatch, repo2)
    result2 = _persist_pipeline_stage(
        tenant_id="default", actor_open_id="ou_user", resource_id="res_2", to_stage="measured",
    )
    assert result2 == {"stage": "measured"}
    content2 = repo2.upserts[0]["content_json"]
    assert content2["stage"] == "measured"
    assert content2["note_url"] == "https://xhslink/keep"  # 保留既有回链


def test_publish_and_performance_notifications_use_bound_resource_version(monkeypatch):
    from data_foundation.studio_api import _persist_backfill, _persist_pipeline_stage
    import data_foundation.studio_api as studio_api

    latest = _FakeResource("res_1", title="C 最新候选", content_text="C 正文")
    exact = _FakeResource("res_1", title="A 已定稿", content_text="A 正文")
    repo = _FakeRepo(
        resources={"res_1": latest},
        metric_id="m1",
        metric_content={
            "stage": "scheduled",
            "target_resource_version": 1,
            "account": "acc_1",
        },
    )
    repo.get_resource_version = lambda tenant_id, actor_open_id, resource_id, resource_version: exact
    _use_fake_repo(monkeypatch, repo)
    draft_sync = {}
    metrics_sync = {}
    monkeypatch.setattr(
        studio_api,
        "_best_effort_feishu_draft",
        lambda actor_open_id, **kwargs: draft_sync.update(kwargs),
    )
    _persist_pipeline_stage(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="res_1",
        to_stage="published",
        link="https://xhslink/a",
    )
    assert repo.upserts[-1]["title"] == "published · A 已定稿"
    assert draft_sync == {"title": "A 已定稿", "content": "A 正文"}

    # 回填重新使用一个已发布 metric，通知标题仍取 target_resource_version=1。
    repo._resources["m1"].content_json["stage"] = "published"
    repo._resources["m1"].content_json["target_resource_version"] = 1
    monkeypatch.setattr(
        studio_api,
        "_best_effort_feishu_metrics",
        lambda actor_open_id, **kwargs: metrics_sync.update(kwargs),
    )
    _persist_backfill(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="res_1",
        target_resource_version=1,
        metrics={"likes": 10},
    )
    assert metrics_sync["title"] == "A 已定稿"


def test_persist_pipeline_stage_rejects_reverse_skip_and_no_start(monkeypatch):
    from data_foundation.studio_api import _persist_pipeline_stage, _StageConflict

    # 逆向 measured→published、跨级 scheduled→measured 一律 _StageConflict
    cases = [
        ("measured", "published"),
        ("published", "scheduled"),
        ("scheduled", "measured"),
    ]
    for current, target in cases:
        repo = _FakeRepo(
            resources={"res_1": _FakeResource("res_1")},
            metric_id="m1",
            metric_content={"stage": current},
        )
        _use_fake_repo(monkeypatch, repo)
        with pytest.raises(_StageConflict):
            _persist_pipeline_stage(
                tenant_id="default", actor_open_id="ou_user", resource_id="res_1",
                to_stage=target, link="https://xhslink/abc",
            )

    # 无起点(未排期 → 无 performance_metric)→ _StageConflict
    repo_no = _FakeRepo(resources={"res_1": _FakeResource("res_1")}, metric_id=None)
    _use_fake_repo(monkeypatch, repo_no)
    with pytest.raises(_StageConflict):
        _persist_pipeline_stage(
            tenant_id="default", actor_open_id="ou_user", resource_id="res_1", to_stage="measured",
        )


def test_persist_backfill_carries_over_account_and_marks_measured(monkeypatch):
    from data_foundation.studio_api import _persist_backfill

    # 既有 scheduled 排期指标(带 account/scheduled_*)→ 回填后应保留归属并标 measured(读写自洽)
    repo = _FakeRepo(
        resources={"res_1": _FakeResource("res_1", title="露营避坑")},
        metric_id="m1",
        metric_content={
            "stage": "scheduled", "account": "acc_1",
            "scheduled_date": "2026-02-12", "scheduled_time": "19:00", "channel": "xiaohongshu",
        },
    )
    _use_fake_repo(monkeypatch, repo)
    result = _persist_backfill(
        tenant_id="default", actor_open_id="ou_user", resource_id="res_1",
        metrics={"likes": 1240, "collects": 340},
    )
    assert "score" in result
    # 最后一次 upsert 为二次合并:stage=measured + 保留 account/scheduled_* + save 写入的 metrics
    final = [
        write["content_json"]
        for write in repo.upserts
        if write["resource_type"] == "performance_metric"
    ][-1]
    assert final["stage"] == "measured"
    assert final["account"] == "acc_1"
    assert final["scheduled_date"] == "2026-02-12"
    assert final["metrics"] == {"likes": 1240, "collects": 340}
    # measured_by 边由 save_performance_metric_resource 建立(发布管线/选题库 GET 经此边回读)
    assert any(e["edge_type"] == "measured_by" for e in repo.edges)
