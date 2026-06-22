from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeUser:
    identity: str


@dataclass(frozen=True)
class RuntimeServerInfo:
    user: RuntimeUser


@dataclass(frozen=True)
class RuntimeIdentityConfig:
    server_info: RuntimeServerInfo


def identity_config(open_id: str) -> RuntimeIdentityConfig:
    return RuntimeIdentityConfig(server_info=RuntimeServerInfo(user=RuntimeUser(identity=open_id)))


def _identity_from_langgraph_user(user: Any) -> str | None:
    """从 LangGraph 注入的认证用户对象取身份(BaseUser.identity,兼容 dict)。"""
    if user is None:
        return None
    identity = getattr(user, "identity", None)
    if identity is None and isinstance(user, dict):
        identity = user.get("identity")
    if isinstance(identity, str) and identity.strip():
        return identity.strip()
    return None


def actor_open_id_from_config(config: Any | None) -> str | None:
    """从工具 config 解析当前用户 open_id —— 只认服务端可信来源。

    安全铁律(与 data_foundation/permissions.actor_from_config 同源):身份只能来自
    服务端 auth 注入的可信字段,**绝不信任** config["configurable"] 里 user_id/open_id
    这类客户端在 run 请求里可任意填写的字段 —— 否则用户能注入他人 open_id,经 lark_cli/
    lark_mcp 用 get_uat(他人) 冒充身份操作飞书(越权)。

    可信来源(两条):
    1. server_info.user.identity —— 脚本/internal API/测试经 identity_config() 构造的对象路径。
    2. config["configurable"]["langgraph_auth_user"] —— LangGraph server 在工具执行上下文
       注入的认证用户(客户端不可伪造)。server 模式下工具收到的是 RunnableConfig(dict),
       走此路径。
    取不到返回 None(飞书工具据此提示"请先授权",不抛错)。
    """
    if config is None:
        return None

    # 路径 1:RuntimeIdentityConfig / 带 server_info 的对象。
    identity = getattr(getattr(getattr(config, "server_info", None), "user", None), "identity", None)
    if isinstance(identity, str) and identity.strip():
        return identity.strip()

    # 路径 2:LangGraph server 注入的可信认证用户(在 configurable 里,客户端不可伪造)。
    if isinstance(config, dict):
        configurable = config.get("configurable")
    else:
        configurable = getattr(config, "configurable", None)
    if isinstance(configurable, dict):
        return _identity_from_langgraph_user(configurable.get("langgraph_auth_user"))

    return None
