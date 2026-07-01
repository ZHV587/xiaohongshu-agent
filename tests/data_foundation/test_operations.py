import data_foundation.tools as tools
import data_foundation.operations as ops


def _cfg(open_id: str):
    # 与现有工具一致:actor_from_config 从 configurable.langgraph_auth_user 解析可信身份。
    return {"configurable": {"langgraph_auth_user": {"identity": open_id}}}


def _patch_loads(monkeypatch):
    monkeypatch.setattr(ops, "load_analytics", lambda *, tenant_id, account: {"dashboard": [], "library": [], "teardown": {"title": "", "points": []}})
    monkeypatch.setattr(ops, "load_calendar", lambda *, tenant_id, account: {"month": {"label": "x", "days": 30, "firstOffset": 0}, "calendar": []})
    monkeypatch.setattr(ops, "load_pipeline", lambda *, tenant_id, account: [])
    monkeypatch.setattr(ops, "load_accounts", lambda *, tenant_id: {"accounts": [], "overview": {"totalFans": 0, "weekNewFans": 0, "weekPosts": 0, "avgHotRate": 0}})
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


def test_recents_and_trends_allow_any_user(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    assert _invoke("recents", open_id="ou_user")["ok"] is True
    assert _invoke("trends", open_id="ou_user")["ok"] is True


def test_matrix_overview_requires_admin(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    # 普通用户读矩阵总览(不带 account)/accounts → 被拒,返回权限提示(非报错、不含数据)
    for view in ("analytics", "calendar", "pipeline", "accounts"):
        out = _invoke(view, account=None, open_id="ou_user")
        assert out["ok"] is False
        assert "admin" in out["error"].lower() or "管理员" in out["error"]
        assert "dashboard" not in out and "accounts" not in out and "queue" not in out


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
