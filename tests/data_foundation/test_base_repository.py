import pytest
from unittest.mock import MagicMock

from data_foundation.db import connect
from data_foundation.models import RuntimeIdentityConfig
from data_foundation.repositories.base import BaseRepository
from data_foundation.repositories.resource import ResourceRepository
from data_foundation import db


def test_readable_resource_where_uses_named_placeholders():
    """片段必须用命名占位符,绝不把身份值拼进 SQL(参数化由 psycopg 绑定)。"""
    repo = BaseRepository()
    fragment = repo.readable_resource_where()
    # 命名占位符在位
    assert "%(tenant_id)s" in fragment
    assert "%(actor_open_id)s" in fragment
    # 无别名时去掉 r. 前缀
    assert "tenant_id = %(tenant_id)s" in fragment
    assert "r.tenant_id" not in fragment
    # 团队可见 / 显式授权分支齐全
    assert "visibility = 'team'" in fragment
    assert "rp.permission in ('read', 'write', 'admin')" in fragment


def test_readable_resource_where_with_alias():
    repo = BaseRepository()
    fragment = repo.readable_resource_where(alias="r")
    assert "r.tenant_id = %(tenant_id)s" in fragment
    assert "r.owner_open_id = %(actor_open_id)s" in fragment
    assert "r.visibility = 'team'" in fragment


def test_readable_resource_where_never_embeds_identity_values():
    """改造核心:身份值不再出现在 SQL 文本里,杜绝注入面与手动转义漂移。"""
    repo = BaseRepository()
    fragment = repo.readable_resource_where(alias="r")
    # 片段是纯模板,不含任何具体身份字面值
    assert "tenant_" not in fragment.replace("tenant_id", "")
    assert "'" in fragment  # 仅 'team'/'user'/permission 等字面常量,无身份值
    # 没有把值拼进来的痕迹
    assert "OR '1'='1" not in fragment


def test_alias_sql_injection_guard():
    repo = BaseRepository()
    # 合法别名通过
    repo.readable_resource_where(alias="r")
    repo.readable_resource_where(alias="res_1")
    repo.readable_resource_where(alias=None)
    # 非法别名拒绝
    with pytest.raises(ValueError, match="Invalid alias"):
        repo.readable_resource_where(alias="r; DROP TABLE resources;")
    with pytest.raises(ValueError, match="Invalid alias"):
        repo.readable_resource_where(alias="r-1")


def test_connection_context_provided():
    repo = BaseRepository()
    mock_conn = MagicMock()
    with repo.connection_context(mock_conn) as conn:
        assert conn is mock_conn
    # Since connection was provided, we must NOT close it
    mock_conn.close.assert_not_called()


def test_connection_context_not_provided(monkeypatch):
    repo = BaseRepository()
    mock_new_conn = MagicMock()
    monkeypatch.setattr(db, "connect", lambda: mock_new_conn)
    with repo.connection_context() as conn:
        assert conn is mock_new_conn
    # Since connection was opened by the repository, it must be closed automatically
    mock_new_conn.close.assert_called_once()


def test_connection_context_closes_on_error(monkeypatch):
    repo = BaseRepository()
    mock_new_conn = MagicMock()
    monkeypatch.setattr(db, "connect", lambda: mock_new_conn)
    with pytest.raises(RuntimeError):
        with repo.connection_context() as conn:
            assert conn is mock_new_conn
            raise RuntimeError("test error")
    # Should still close the connection on error
    mock_new_conn.close.assert_called_once()


# --- 集成:真库验证参数绑定杜绝注入越权(CI 设 TEST_XHS_DATABASE_URL 时真跑) ---

def test_malicious_tenant_is_bound_not_injected(migrated_conn):
    """恶意 tenant_id 被当作普通值绑定:既查不到他人资源,也不触发注入越权。"""
    repo = ResourceRepository(migrated_conn)
    victim = repo.upsert_resource(
        tenant_id="real_tenant",
        actor_open_id="victim",
        resource_type="note",
        title="victim secret",
        content_text="secret body",
        visibility="private",
    )

    # 经典注入串作为 tenant_id:若被拼进 SQL 会绕过租户边界;参数化下只是个查不到的值。
    injected = repo.get_resource(
        "real_tenant' OR '1'='1",
        "attacker",
        victim.id,
        conn=migrated_conn,
    )
    assert injected is None

    # 正主仍可读自己的资源(回归:参数化未破坏正常 ACL)。
    legit = repo.get_resource("real_tenant", "victim", victim.id, conn=migrated_conn)
    assert legit is not None
    assert legit.id == victim.id
