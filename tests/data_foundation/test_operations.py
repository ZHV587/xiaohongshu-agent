import inspect

import data_foundation.tools as tools
import data_foundation.operations as ops


def test_calendar_and_pipeline_sql_hydrate_bound_copy_version():
    calendar_source = inspect.getsource(ops._load_schedule_items)
    pipeline_source = inspect.getsource(ops.load_pipeline)
    for source in (calendar_source, pipeline_source):
        assert "resource_versions cv" in source
        assert "resource_contexts context" in source
        assert "context.account_id" in source
        assert "e.source_resource_version" in source
        assert "cv.content_json->>'title'" in source
        assert 'content.get("account")' not in source


def test_analytics_filters_real_rows_by_exact_resource_context():
    source = inspect.getsource(ops.load_analytics)
    assert "resource_contexts context" in source
    assert "context.account_id" in source
    assert "latest_metric" in source
    assert "return {\"dashboard\": []" not in source


def test_accounts_aggregation_is_owner_scoped():
    source = inspect.getsource(ops.load_accounts)
    assert "account.owner_open_id = %s" in source
    assert "actor_open_id" in source
    assert '"writingNiche": str(row["niche"]) if row["niche"] else None' in source


def _cfg(open_id: str):
    # 与现有工具一致:actor_from_config 从 configurable.langgraph_auth_user 解析可信身份。
    return {"configurable": {"langgraph_auth_user": {"identity": open_id}}}


def _patch_loads(monkeypatch):
    monkeypatch.setattr(
        ops,
        "load_owned_account_context",
        lambda *, tenant_id, actor_open_id, account: None,
    )
    monkeypatch.setattr(ops, "load_analytics", lambda *, tenant_id, account: {"dashboard": [], "library": [], "teardown": {"title": "", "points": []}})
    monkeypatch.setattr(ops, "load_calendar", lambda *, tenant_id, account: {"month": {"label": "x", "days": 30, "firstOffset": 0}, "calendar": []})
    monkeypatch.setattr(ops, "load_pipeline", lambda *, tenant_id, account: [])
    monkeypatch.setattr(ops, "load_accounts", lambda *, tenant_id, actor_open_id: {"accounts": [], "overview": {"totalFans": 0, "weekNewFans": 0, "weekPosts": 0, "avgHotRate": 0}})
    monkeypatch.setattr(ops, "load_recents", lambda *, tenant_id, open_id: [])
    monkeypatch.setattr(ops, "load_trends", lambda *, tenant_id: [])


def _invoke(view, account=None, open_id="ou_user"):
    # @tool 包装后用 .func 取原函数直测(不经 agent runtime)。
    return tools.get_operations_data.func(view=view, account=account, config=_cfg(open_id))


def test_single_account_views_allow_any_user(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    for view in ("analytics", "calendar", "pipeline"):
        out = _invoke(view, account="acc_1", open_id="ou_user")
        assert out["ok"] is True and out["view"] == view


def test_single_account_views_reject_unowned_account(monkeypatch):
    _patch_loads(monkeypatch)

    def _forbidden(**_kwargs):
        raise PermissionError("not owned")

    monkeypatch.setattr(ops, "load_owned_account_context", _forbidden)
    out = _invoke("analytics", account="11111111-1111-4111-8111-111111111111")
    assert out == {"ok": False, "error": "无权访问该账号。"}


def test_recents_and_trends_allow_any_user(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    assert _invoke("recents", open_id="ou_user")["ok"] is True
    assert _invoke("trends", open_id="ou_user")["ok"] is True


def test_matrix_overview_requires_admin(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    # 普通用户读跨用户矩阵总览(不带 account)→ 被拒；accounts 是 owner-scoped 例外。
    for view in ("analytics", "calendar", "pipeline"):
        out = _invoke(view, account=None, open_id="ou_user")
        assert out["ok"] is False
        assert "admin" in out["error"].lower() or "管理员" in out["error"]
        assert (
            "dashboard" not in out
            and "accounts" not in out
            and "queue" not in out
            and "month" not in out
            and "library" not in out
        )
    accounts = _invoke("accounts", account=None, open_id="ou_user")
    assert accounts["ok"] is True and accounts["accounts"] == []


def test_matrix_overview_allows_admin(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    for view in ("analytics", "calendar", "pipeline", "accounts"):
        out = _invoke(view, account=None, open_id="ou_admin")
        assert out["ok"] is True


def test_unknown_view_rejected(monkeypatch):
    _patch_loads(monkeypatch)
    out = _invoke("bogus", open_id="ou_user")
    assert out["ok"] is False and "view" in out["error"].lower()


def test_load_failure_redacts_dsn(monkeypatch):
    # load_* 抛含 DSN 的异常时,工具须返回通用不可用提示,响应内容不得含 DSN/异常细节
    # (与 BFF handler 的反泄露口径一致:ToolNode 会把异常原文注入模型上下文再转告用户)。
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")

    def _boom(*, tenant_id, account):
        raise RuntimeError("postgresql://user:db-secret@host/db")

    monkeypatch.setattr(ops, "load_analytics", _boom)
    out = _invoke("analytics", account="acc_1", open_id="ou_user")
    assert out["ok"] is False
    assert "db-secret" not in str(out)
    assert "postgresql://" not in str(out)
