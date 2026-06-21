from __future__ import annotations

import os
from typing import Any


def default_tenant_id() -> str:
    return os.environ.get("XHS_DEFAULT_TENANT_ID", "default")


def _identity_from_langgraph_user(user: Any) -> str | None:
    """从 LangGraph 注入的认证用户对象取身份。

    BaseUser 暴露 .identity;也兼容 dict 形态({"identity": ...})。
    """
    if user is None:
        return None
    identity = getattr(user, "identity", None)
    if identity is None and isinstance(user, dict):
        identity = user.get("identity")
    if isinstance(identity, str) and identity.strip():
        return identity.strip()
    return None


def actor_from_config(config: Any) -> str:
    # 路径 1:RuntimeIdentityConfig / server_info(脚本、internal API、测试用 identity_config)。
    identity = getattr(getattr(getattr(config, "server_info", None), "user", None), "identity", None)
    if isinstance(identity, str) and identity.strip():
        return identity.strip()

    # 路径 2:LangGraph server 在 tool 执行上下文把认证用户注入到
    # config["configurable"]["langgraph_auth_user"](服务端 auth 注入,客户端不可伪造)。
    # 注意:绝不能信任 configurable 里 user_id/open_id 之类客户端可传的字段。
    configurable = None
    if isinstance(config, dict):
        configurable = config.get("configurable")
    else:
        configurable = getattr(config, "configurable", None)
    if isinstance(configurable, dict):
        resolved = _identity_from_langgraph_user(configurable.get("langgraph_auth_user"))
        if resolved:
            return resolved

    raise PermissionError("Missing LangGraph user identity")


def readable_resource_where(alias: str = "r") -> str:
    return f"""
    {alias}.tenant_id = %(tenant_id)s
    and (
      {alias}.owner_open_id = %(actor_open_id)s
      or {alias}.visibility = 'team'
      or exists (
        select 1 from resource_permissions rp
        where rp.resource_id = {alias}.id
          and rp.tenant_id = {alias}.tenant_id
          and rp.subject_type = 'user'
          and rp.subject_id = %(actor_open_id)s
          and rp.permission in ('read', 'write', 'admin')
      )
      or %(actor_open_id)s = any(regexp_split_to_array(coalesce(current_setting('app.admin_open_ids', true), ''), '\\s*,\\s*'))
    )
    """
