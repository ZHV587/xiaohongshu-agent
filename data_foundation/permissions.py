from __future__ import annotations

import os
from typing import Any


def default_tenant_id() -> str:
    return os.environ.get("XHS_DEFAULT_TENANT_ID", "default")


def actor_from_config(config: Any) -> str:
    identity = getattr(getattr(getattr(config, "server_info", None), "user", None), "identity", None)
    if not identity:
        raise PermissionError("Missing LangGraph user identity")
    return str(identity)


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
