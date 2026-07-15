from __future__ import annotations

import json
from typing import Any
import uuid

from psycopg.rows import dict_row

from data_foundation.repositories.base import BaseRepository
from data_foundation.writing_context import WritingContext


class AccountRepository(BaseRepository):
    """真实小红书账号实体与精确资源上下文。"""

    def upsert_account(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        display_name: str,
        platform_account_id: str | None = None,
        niche: str | None = None,
        account_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        make_default: bool = False,
    ) -> dict[str, Any]:
        name = display_name.strip() if isinstance(display_name, str) else ""
        if not name:
            raise ValueError("display_name is required")
        context = WritingContext(account_id=account_id, niche=niche)
        normalized_account = context.account_id or str(uuid.uuid4())
        platform = (
            platform_account_id.strip()
            if isinstance(platform_account_id, str) and platform_account_id.strip()
            else None
        )
        with self.connection_context() as connection:
            with connection.transaction():
                if context.account_id is not None:
                    owner = connection.execute(
                        """
                        select tenant_id, owner_open_id
                        from xhs_accounts
                        where id = %s
                        """,
                        (context.account_id,),
                    ).fetchone()
                    if owner is not None and (
                        owner["tenant_id"] != tenant_id
                        or owner["owner_open_id"] != actor_open_id
                    ):
                        raise PermissionError("account_id is not owned by current actor")
                if platform is not None:
                    existing_platform = connection.execute(
                        """
                        select id::text
                        from xhs_accounts
                        where tenant_id = %s and owner_open_id = %s
                          and platform_account_id = %s
                        for update
                        """,
                        (tenant_id, actor_open_id, platform),
                    ).fetchone()
                    if existing_platform is not None:
                        existing_id = str(existing_platform["id"])
                        if context.account_id is not None and existing_id != context.account_id:
                            raise ValueError(
                                "platform_account_id already belongs to another account"
                            )
                        normalized_account = existing_id
                if make_default:
                    connection.execute(
                        """
                        update xhs_accounts set is_default = false, updated_at = now()
                        where tenant_id = %s and owner_open_id = %s and is_default is true
                        """,
                        (tenant_id, actor_open_id),
                    )
                row = connection.execute(
                    """
                    insert into xhs_accounts (
                      id, tenant_id, owner_open_id, platform_account_id,
                      display_name, niche, is_default, metadata
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    on conflict (tenant_id, owner_open_id, id) do update
                    set platform_account_id = excluded.platform_account_id,
                        display_name = excluded.display_name,
                        niche = excluded.niche,
                        is_default = excluded.is_default or xhs_accounts.is_default,
                        metadata = excluded.metadata,
                        status = 'active',
                        updated_at = now()
                    returning *
                    """,
                    (
                        normalized_account,
                        tenant_id,
                        actor_open_id,
                        platform,
                        name,
                        context.niche,
                        make_default,
                        json.dumps(dict(metadata or {}), ensure_ascii=False, sort_keys=True),
                    ),
                ).fetchone()
        return dict(row)

    def list_accounts(
        self, *, tenant_id: str, actor_open_id: str | None = None
    ) -> list[dict[str, Any]]:
        params: list[Any] = [tenant_id]
        owner_filter = ""
        if actor_open_id is not None:
            owner_filter = "and owner_open_id = %s"
            params.append(actor_open_id)
        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    select id::text, owner_open_id, platform_account_id, display_name,
                           niche, is_default, status, metadata, created_at, updated_at
                    from xhs_accounts
                    where tenant_id = %s and status = 'active' {owner_filter}
                    order by is_default desc, updated_at desc, id
                    """,
                    params,
                ).fetchall()
        return [dict(row) for row in rows]

    def assert_owned_context(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        context: WritingContext,
    ) -> None:
        if context.account_id is None:
            return
        with self.connection_context() as connection:
            row = connection.execute(
                """
                select 1 from xhs_accounts
                where tenant_id = %s and owner_open_id = %s and id = %s
                  and status = 'active'
                """,
                (tenant_id, actor_open_id, context.account_id),
            ).fetchone()
        if row is None:
            raise PermissionError("account context is not owned by current actor")

    def get_owned_context(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        account_id: str,
    ) -> WritingContext:
        """读取当前用户的有效账号上下文，并以账号表中的垂类为准。"""
        requested = WritingContext(account_id=account_id)
        with self.connection_context() as connection:
            row = connection.execute(
                """
                select id::text as account_id, niche
                from xhs_accounts
                where tenant_id = %s and owner_open_id = %s and id = %s
                  and status = 'active'
                """,
                (tenant_id, actor_open_id, requested.account_id),
            ).fetchone()
        if row is None:
            raise PermissionError("account context is not owned by current actor")
        return WritingContext(account_id=row["account_id"], niche=row["niche"])

    def attach_resource_context(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        context: WritingContext,
        source: str,
    ) -> None:
        if context.is_global:
            return
        if source not in {"frontend", "account_default", "source_metadata", "inherited"}:
            raise ValueError("unsupported resource context source")
        self.assert_owned_context(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            context=context,
        )
        with self.connection_context() as connection:
            inserted = connection.execute(
                """
                insert into resource_contexts (
                  tenant_id, resource_id, resource_version, owner_open_id,
                  account_id, niche, scope_key, context_source
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (tenant_id, resource_id, resource_version) do nothing
                returning account_id::text, niche, scope_key
                """,
                (
                    tenant_id,
                    resource_id,
                    resource_version,
                    actor_open_id,
                    context.account_id,
                    context.niche,
                    context.scope_key,
                    source,
                ),
            ).fetchone()
            if inserted is not None:
                return
            existing = connection.execute(
                """
                select owner_open_id, account_id::text, niche, scope_key
                from resource_contexts
                where tenant_id = %s and resource_id = %s and resource_version = %s
                """,
                (tenant_id, resource_id, resource_version),
            ).fetchone()
        if existing is None:
            raise RuntimeError("resource context insert lost without a conflicting row")
        if (
            existing["owner_open_id"] != actor_open_id
            or existing["account_id"] != context.account_id
            or existing["niche"] != context.niche
            or existing["scope_key"] != context.scope_key
        ):
            raise ResourceContextConflict(
                "exact resource version is already bound to another writing context"
            )

    def bind_resource_to_account(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        account_id: str,
        source: str,
    ) -> WritingContext:
        """给精确版本绑定账号；同账号重试幂等，禁止换账号覆盖不可变事实。"""
        owned = self.get_owned_context(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            account_id=account_id,
        )
        with self.connection_context() as connection:
            row = connection.execute(
                """
                select owner_open_id, account_id::text, niche
                from resource_contexts
                where tenant_id = %s and resource_id = %s and resource_version = %s
                """,
                (tenant_id, resource_id, resource_version),
            ).fetchone()
        if row is not None:
            if row["owner_open_id"] != actor_open_id or row["account_id"] != owned.account_id:
                raise ResourceContextConflict(
                    "exact resource version is already bound to another account"
                )
            # 账号垂类后来被修改时，精确版本仍保留创作当时的不可变垂类事实。
            return WritingContext(account_id=row["account_id"], niche=row["niche"])
        self.attach_resource_context(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=resource_id,
            resource_version=resource_version,
            context=owned,
            source=source,
        )
        return owned

    def get_resource_context(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        actor_open_id: str | None = None,
    ) -> WritingContext:
        with self.connection_context() as connection:
            row = connection.execute(
                """
                select account_id::text, niche
                from resource_contexts
                where tenant_id = %s and resource_id = %s and resource_version = %s
                  and (%s::text is null or owner_open_id = %s::text)
                """,
                (
                    tenant_id,
                    resource_id,
                    resource_version,
                    actor_open_id,
                    actor_open_id,
                ),
            ).fetchone()
        return (
            WritingContext()
            if row is None
            else WritingContext(account_id=row["account_id"], niche=row["niche"])
        )


class ResourceContextConflict(ValueError):
    """同一不可变资源版本被请求绑定到不同账号或垂类。"""


__all__ = ["AccountRepository", "ResourceContextConflict"]
