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


def _identity_from_config_object(config: Any) -> str | None:
    """从单个 config 对象解析身份(不抛错,取不到返回 None)。"""
    if config is None:
        return None

    # 路径 1:RuntimeIdentityConfig / server_info(脚本、internal API、测试用 identity_config)。
    identity = getattr(getattr(getattr(config, "server_info", None), "user", None), "identity", None)
    if isinstance(identity, str) and identity.strip():
        return identity.strip()

    # 路径 2:LangGraph 在 tool 执行上下文把认证用户注入到
    # config["configurable"]["langgraph_auth_user"](服务端 auth 注入,客户端不可伪造)。
    # 注意:绝不能信任 configurable 里 user_id/open_id 之类客户端可传的字段。
    if isinstance(config, dict):
        configurable = config.get("configurable")
    else:
        configurable = getattr(config, "configurable", None)
    if isinstance(configurable, dict):
        return _identity_from_langgraph_user(configurable.get("langgraph_auth_user"))
    return None


def actor_from_config(config: Any) -> str:
    # 先用工具收到的 config 参数解析。
    resolved = _identity_from_config_object(config)
    if resolved:
        return resolved

    # Fallback:并发工具调用(asyncio.gather + run_in_executor 线程池)下,显式 config
    # 参数可能丢失 configurable/身份(contextvar 在子线程传播的竞态)。改用 LangGraph
    # 官方的 get_config() 从运行时 contextvar 兜底取认证用户,确保身份解析稳定。
    try:
        from langgraph.config import get_config

        resolved = _identity_from_config_object(get_config())
        if resolved:
            return resolved
    except Exception:
        # get_config() 在非 LangGraph 运行时(脚本/部分测试)会抛 RuntimeError,忽略走最终拒绝。
        pass

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
