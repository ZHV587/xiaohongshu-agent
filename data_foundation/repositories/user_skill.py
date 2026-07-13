from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any, Optional

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.models import UserSkill, UserSkillAuditEvent, UserSkillVersion
from data_foundation.repositories.base import BaseRepository


class UserSkillRepository(BaseRepository):
    """用户级 Skill 配置仓储。

    Skill 配置刻意不复用 ``resources``：它不会产生 resource_outbox 事件，也不会
    进入内容全文、向量或图索引。所有公开方法都要求 tenant + owner 双重作用域，
    未命中统一返回不存在，避免泄露其他用户的 Skill 是否存在。
    """

    MAX_DISPLAY_NAME = 80
    MAX_DESCRIPTION = 500
    MAX_INSTRUCTIONS = 32 * 1024

    def create_skill(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        display_name: str,
        description: str,
        instructions_markdown: str,
        trigger_examples: list[str] | None = None,
        non_trigger_examples: list[str] | None = None,
        tags: list[str] | None = None,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        tenant_id, owner_open_id, actor_open_id = self._validate_identity(
            tenant_id, owner_open_id, actor_open_id
        )
        display_name, description, instructions_markdown = self._validate_definition(
            display_name, description, instructions_markdown
        )
        skill_id = uuid.uuid4()
        version_id = uuid.uuid4()
        runtime_name = self._runtime_name(owner_open_id, skill_id)
        trigger_examples = list(trigger_examples or [])
        non_trigger_examples = list(non_trigger_examples or [])
        tags = list(tags or [])
        content_hash = self._content_hash(
            display_name, description, instructions_markdown,
            trigger_examples, non_trigger_examples, tags,
        )

        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        insert into user_skills
                          (id, tenant_id, owner_open_id, runtime_name, current_name,
                           current_name_key, latest_version)
                        values (%s, %s, %s, %s, %s, %s, 1)
                        """,
                        (
                            skill_id,
                            tenant_id,
                            owner_open_id,
                            runtime_name,
                            display_name,
                            self._name_key(display_name),
                        ),
                    )
                    cursor.execute(
                        """
                        insert into user_skill_versions
                          (id, tenant_id, owner_open_id, skill_id, version, display_name,
                           description, instructions_markdown, trigger_examples,
                           non_trigger_examples, tags, content_hash, created_by_open_id)
                        values (%s, %s, %s, %s, 1, %s, %s, %s, %s::jsonb,
                                %s::jsonb, %s::jsonb, %s, %s)
                        """,
                        (
                            version_id,
                            tenant_id,
                            owner_open_id,
                            skill_id,
                            display_name,
                            description,
                            instructions_markdown,
                            json.dumps(trigger_examples, ensure_ascii=False),
                            json.dumps(non_trigger_examples, ensure_ascii=False),
                            json.dumps(tags, ensure_ascii=False),
                            content_hash,
                            actor_open_id,
                        ),
                    )
                    cursor.execute(
                        """
                        insert into user_skill_publications
                          (tenant_id, owner_open_id, skill_id, status, updated_by_open_id)
                        values (%s, %s, %s, 'draft', %s)
                        """,
                        (tenant_id, owner_open_id, skill_id, actor_open_id),
                    )
                    cursor.execute(
                        """
                        insert into user_skill_revisions
                          (tenant_id, owner_open_id, revision)
                        values (%s, %s, 0)
                        on conflict (tenant_id, owner_open_id) do nothing
                        """,
                        (tenant_id, owner_open_id),
                    )
                    self._append_audit(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=str(skill_id),
                        event_type="created",
                        actor_open_id=actor_open_id,
                        skill_version=1,
                        payload={"content_hash": content_hash},
                    )
            return self.get_skill(
                tenant_id=tenant_id,
                owner_open_id=owner_open_id,
                skill_id=str(skill_id),
                conn=connection,
            )

    def append_version(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        display_name: str,
        description: str,
        instructions_markdown: str,
        trigger_examples: list[str] | None = None,
        non_trigger_examples: list[str] | None = None,
        tags: list[str] | None = None,
        expected_latest_version: int | None = None,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        tenant_id, owner_open_id, actor_open_id = self._validate_identity(
            tenant_id, owner_open_id, actor_open_id
        )
        display_name, description, instructions_markdown = self._validate_definition(
            display_name, description, instructions_markdown
        )
        skill_id = self._validate_uuid(skill_id)
        trigger_examples = list(trigger_examples or [])
        non_trigger_examples = list(non_trigger_examples or [])
        tags = list(tags or [])
        content_hash = self._content_hash(
            display_name, description, instructions_markdown,
            trigger_examples, non_trigger_examples, tags,
        )

        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    head = self._lock_head(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                    )
                    if head["status"] == "archived":
                        raise ValueError("Archived skills cannot be edited")
                    current_version = int(head["latest_version"])
                    if (
                        expected_latest_version is not None
                        and expected_latest_version != current_version
                    ):
                        raise RuntimeError("Skill version conflict")
                    latest = cursor.execute(
                        """
                        select content_hash
                        from user_skill_versions
                        where tenant_id = %s and owner_open_id = %s
                          and skill_id = %s and version = %s
                        """,
                        (tenant_id, owner_open_id, skill_id, current_version),
                    ).fetchone()
                    if latest and latest["content_hash"] == content_hash:
                        raise ValueError("Skill definition is unchanged")

                    new_version = current_version + 1
                    cursor.execute(
                        """
                        insert into user_skill_versions
                          (tenant_id, owner_open_id, skill_id, version, display_name,
                           description, instructions_markdown, trigger_examples,
                           non_trigger_examples, tags, content_hash, created_by_open_id)
                        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                                %s::jsonb, %s::jsonb, %s, %s)
                        """,
                        (
                            tenant_id,
                            owner_open_id,
                            skill_id,
                            new_version,
                            display_name,
                            description,
                            instructions_markdown,
                            json.dumps(trigger_examples, ensure_ascii=False),
                            json.dumps(non_trigger_examples, ensure_ascii=False),
                            json.dumps(tags, ensure_ascii=False),
                            content_hash,
                            actor_open_id,
                        ),
                    )
                    cursor.execute(
                        """
                        update user_skills
                        set latest_version = %s, current_name = %s, current_name_key = %s,
                            updated_at = now()
                        where tenant_id = %s and owner_open_id = %s and id = %s
                        """,
                        (
                            new_version,
                            display_name,
                            self._name_key(display_name),
                            tenant_id,
                            owner_open_id,
                            skill_id,
                        ),
                    )
                    self._append_audit(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                        event_type="version_created",
                        actor_open_id=actor_open_id,
                        skill_version=new_version,
                        payload={
                            "previous_version": current_version,
                            "content_hash": content_hash,
                        },
                    )
            return self.get_skill(
                tenant_id=tenant_id,
                owner_open_id=owner_open_id,
                skill_id=skill_id,
                conn=connection,
            )

    def publish_version(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        version: int | None = None,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        tenant_id, owner_open_id, actor_open_id = self._validate_identity(
            tenant_id, owner_open_id, actor_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        if version is not None and (
            isinstance(version, bool) or not isinstance(version, int) or version < 1
        ):
            raise ValueError("Publish version must be a positive integer")

        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    head = self._lock_head(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                    )
                    if head["status"] == "archived":
                        raise ValueError("Archived skills cannot be published")
                    target_version = int(version or head["latest_version"])
                    target = cursor.execute(
                        """
                        select 1
                        from user_skill_versions
                        where tenant_id = %s and owner_open_id = %s
                          and skill_id = %s and version = %s
                        """,
                        (tenant_id, owner_open_id, skill_id, target_version),
                    ).fetchone()
                    if not target:
                        raise KeyError("Skill version not found")

                    previous_status = str(head["status"])
                    previous_version = head["published_version"]
                    if previous_status == "published" and previous_version == target_version:
                        return self.get_skill(
                            tenant_id=tenant_id,
                            owner_open_id=owner_open_id,
                            skill_id=skill_id,
                            conn=connection,
                        )

                    if previous_status == "disabled" and previous_version != target_version:
                        raise ValueError("Enable the Skill before publishing another version")
                    if previous_version is not None and target_version < int(previous_version):
                        raise ValueError("Use rollback to select an older published version")

                    if previous_status == "disabled" and previous_version == target_version:
                        event_type = "enabled"
                    else:
                        event_type = "published"

                    cursor.execute(
                        """
                        update user_skill_publications
                        set status = 'published', published_version = %s,
                            published_at = now(), disabled_at = null, archived_at = null,
                            updated_by_open_id = %s, updated_at = now()
                        where tenant_id = %s and owner_open_id = %s and skill_id = %s
                        """,
                        (target_version, actor_open_id, tenant_id, owner_open_id, skill_id),
                    )
                    self._touch_skill(cursor, tenant_id, owner_open_id, skill_id)
                    catalog_revision = self._bump_catalog_revision(
                        cursor, tenant_id=tenant_id, owner_open_id=owner_open_id
                    )
                    self._append_audit(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                        event_type=event_type,
                        actor_open_id=actor_open_id,
                        skill_version=target_version,
                        payload={
                            "previous_status": previous_status,
                            "previous_published_version": previous_version,
                            "catalog_revision": catalog_revision,
                        },
                    )
            return self.get_skill(
                tenant_id=tenant_id,
                owner_open_id=owner_open_id,
                skill_id=skill_id,
                conn=connection,
            )

    def disable_skill(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        return self._change_status(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
            actor_open_id=actor_open_id,
            skill_id=skill_id,
            target_status="disabled",
            conn=conn,
        )

    def rollback_version(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        version: int,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        tenant_id, owner_open_id, actor_open_id = self._validate_identity(
            tenant_id, owner_open_id, actor_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Rollback version must be a positive integer")
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    head = self._lock_head(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                    )
                    if head["status"] not in {"published", "disabled"}:
                        raise ValueError("Only published or disabled skills can be rolled back")
                    if head["published_version"] == version:
                        return self.get_skill(
                            tenant_id=tenant_id, owner_open_id=owner_open_id,
                            skill_id=skill_id, conn=connection,
                        )
                    previously_published = cursor.execute(
                        """
                        select 1 from user_skill_audit_events
                        where tenant_id = %s and owner_open_id = %s and skill_id = %s
                          and skill_version = %s
                          and event_type in ('published', 'rolled_back', 'enabled')
                        limit 1
                        """,
                        (tenant_id, owner_open_id, skill_id, version),
                    ).fetchone()
                    if not previously_published:
                        raise ValueError("Rollback target was never published")
                    previous_version = int(head["published_version"])
                    cursor.execute(
                        """
                        update user_skill_publications
                        set published_version = %s, updated_by_open_id = %s, updated_at = now()
                        where tenant_id = %s and owner_open_id = %s and skill_id = %s
                        """,
                        (version, actor_open_id, tenant_id, owner_open_id, skill_id),
                    )
                    self._touch_skill(cursor, tenant_id, owner_open_id, skill_id)
                    catalog_revision = self._bump_catalog_revision(
                        cursor, tenant_id=tenant_id, owner_open_id=owner_open_id
                    )
                    self._append_audit(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                        event_type="rolled_back",
                        actor_open_id=actor_open_id,
                        skill_version=version,
                        payload={
                            "previous_published_version": previous_version,
                            "preserved_status": head["status"],
                            "catalog_revision": catalog_revision,
                        },
                    )
            return self.get_skill(
                tenant_id=tenant_id, owner_open_id=owner_open_id,
                skill_id=skill_id, conn=connection,
            )

    def archive_skill(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        return self._change_status(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
            actor_open_id=actor_open_id,
            skill_id=skill_id,
            target_status="archived",
            conn=conn,
        )

    def get_skill(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        skill_id: str,
        conn: Optional[Connection] = None,
    ) -> UserSkill:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    self._skill_select_sql()
                    + " where s.tenant_id = %s and s.owner_open_id = %s and s.id = %s",
                    (tenant_id, owner_open_id, skill_id),
                ).fetchone()
                if not row:
                    raise KeyError("Skill not found")
                return self._skill_from_row(row)

    def list_skills(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        include_archived: bool = False,
        conn: Optional[Connection] = None,
    ) -> list[UserSkill]:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        archived_filter = "" if include_archived else " and p.status <> 'archived'"
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    self._skill_select_sql()
                    + " where s.tenant_id = %s and s.owner_open_id = %s"
                    + archived_filter
                    + " order by s.updated_at desc, s.id desc",
                    (tenant_id, owner_open_id),
                ).fetchall()
                return [self._skill_from_row(row) for row in rows]

    def get_published_version(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        skill_id: str,
        conn: Optional[Connection] = None,
    ) -> UserSkillVersion:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    select v.*
                    from user_skill_publications p
                    join user_skill_versions v
                      on v.tenant_id = p.tenant_id
                     and v.owner_open_id = p.owner_open_id
                     and v.skill_id = p.skill_id
                     and v.version = p.published_version
                    where p.tenant_id = %s and p.owner_open_id = %s
                      and p.skill_id = %s and p.status = 'published'
                    """,
                    (tenant_id, owner_open_id, skill_id),
                ).fetchone()
                if not row:
                    raise KeyError("Published skill not found")
                return self._version_from_row(row)

    def list_published_versions(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        conn: Optional[Connection] = None,
    ) -> list[UserSkillVersion]:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select v.*
                    from user_skill_publications p
                    join user_skill_versions v
                      on v.tenant_id = p.tenant_id
                     and v.owner_open_id = p.owner_open_id
                     and v.skill_id = p.skill_id
                     and v.version = p.published_version
                    where p.tenant_id = %s and p.owner_open_id = %s
                      and p.status = 'published'
                    order by p.updated_at desc, p.skill_id desc
                    """,
                    (tenant_id, owner_open_id),
                ).fetchall()
                return [self._version_from_row(row) for row in rows]

    def list_versions(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        skill_id: str,
        conn: Optional[Connection] = None,
    ) -> list[UserSkillVersion]:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                exists = cursor.execute(
                    """
                    select 1 from user_skills
                    where tenant_id = %s and owner_open_id = %s and id = %s
                    """,
                    (tenant_id, owner_open_id, skill_id),
                ).fetchone()
                if not exists:
                    raise KeyError("Skill not found")
                rows = cursor.execute(
                    """
                    select * from user_skill_versions
                    where tenant_id = %s and owner_open_id = %s and skill_id = %s
                    order by version desc
                    """,
                    (tenant_id, owner_open_id, skill_id),
                ).fetchall()
                return [self._version_from_row(row) for row in rows]

    def get_catalog_revision(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        conn: Optional[Connection] = None,
    ) -> int:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        with self.connection_context(conn) as connection:
            row = connection.execute(
                """
                select revision
                from user_skill_revisions
                where tenant_id = %s and owner_open_id = %s
                """,
                (tenant_id, owner_open_id),
            ).fetchone()
            return int(row["revision"] if row else 0)

    def list_audit_events(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        skill_id: str,
        limit: int = 100,
        conn: Optional[Connection] = None,
    ) -> list[UserSkillAuditEvent]:
        tenant_id, owner_open_id, _ = self._validate_identity(
            tenant_id, owner_open_id, owner_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select *
                    from user_skill_audit_events
                    where tenant_id = %s and owner_open_id = %s and skill_id = %s
                    order by created_at desc, id desc
                    limit %s
                    """,
                    (tenant_id, owner_open_id, skill_id, limit),
                ).fetchall()
                return [self._audit_from_row(row) for row in rows]

    def _change_status(
        self,
        *,
        tenant_id: str,
        owner_open_id: str,
        actor_open_id: str,
        skill_id: str,
        target_status: str,
        conn: Optional[Connection],
    ) -> UserSkill:
        tenant_id, owner_open_id, actor_open_id = self._validate_identity(
            tenant_id, owner_open_id, actor_open_id
        )
        skill_id = self._validate_uuid(skill_id)
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    head = self._lock_head(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                    )
                    current_status = str(head["status"])
                    if current_status == target_status:
                        return self.get_skill(
                            tenant_id=tenant_id,
                            owner_open_id=owner_open_id,
                            skill_id=skill_id,
                            conn=connection,
                        )
                    if target_status == "disabled" and current_status != "published":
                        raise ValueError("Only published skills can be disabled")
                    if current_status == "archived":
                        raise ValueError("Archived skills cannot change status")

                    timestamp_column = "disabled_at" if target_status == "disabled" else "archived_at"
                    # timestamp_column is chosen from the fixed set above, never from user input.
                    cursor.execute(
                        f"""
                        update user_skill_publications
                        set status = %s, {timestamp_column} = now(),
                            updated_by_open_id = %s, updated_at = now()
                        where tenant_id = %s and owner_open_id = %s and skill_id = %s
                        """,
                        (target_status, actor_open_id, tenant_id, owner_open_id, skill_id),
                    )
                    if target_status == "archived":
                        cursor.execute(
                            """
                            update user_skills set archived_at = now(), updated_at = now()
                            where tenant_id = %s and owner_open_id = %s and id = %s
                            """,
                            (tenant_id, owner_open_id, skill_id),
                        )
                    else:
                        self._touch_skill(cursor, tenant_id, owner_open_id, skill_id)
                    catalog_revision = self._bump_catalog_revision(
                        cursor, tenant_id=tenant_id, owner_open_id=owner_open_id
                    )
                    self._append_audit(
                        cursor,
                        tenant_id=tenant_id,
                        owner_open_id=owner_open_id,
                        skill_id=skill_id,
                        event_type=target_status,
                        actor_open_id=actor_open_id,
                        skill_version=head["published_version"] or head["latest_version"],
                        payload={
                            "previous_status": current_status,
                            "catalog_revision": catalog_revision,
                        },
                    )
            return self.get_skill(
                tenant_id=tenant_id,
                owner_open_id=owner_open_id,
                skill_id=skill_id,
                conn=connection,
            )

    @staticmethod
    def _lock_head(cursor, *, tenant_id: str, owner_open_id: str, skill_id: str) -> dict:
        row = cursor.execute(
            """
            select s.latest_version, p.status, p.published_version
            from user_skills s
            join user_skill_publications p
              on p.tenant_id = s.tenant_id
             and p.owner_open_id = s.owner_open_id
             and p.skill_id = s.id
            where s.tenant_id = %s and s.owner_open_id = %s and s.id = %s
            for update of s
            """,
            (tenant_id, owner_open_id, skill_id),
        ).fetchone()
        if not row:
            raise KeyError("Skill not found")
        return row

    @staticmethod
    def _touch_skill(cursor, tenant_id: str, owner_open_id: str, skill_id: str) -> None:
        cursor.execute(
            """
            update user_skills set updated_at = now()
            where tenant_id = %s and owner_open_id = %s and id = %s
            """,
            (tenant_id, owner_open_id, skill_id),
        )

    @staticmethod
    def _bump_catalog_revision(cursor, *, tenant_id: str, owner_open_id: str) -> int:
        row = cursor.execute(
            """
            insert into user_skill_revisions
              (tenant_id, owner_open_id, revision)
            values (%s, %s, 1)
            on conflict (tenant_id, owner_open_id) do update
            set revision = user_skill_revisions.revision + 1,
                updated_at = now()
            returning revision
            """,
            (tenant_id, owner_open_id),
        ).fetchone()
        return int(row["revision"])

    @staticmethod
    def _append_audit(
        cursor,
        *,
        tenant_id: str,
        owner_open_id: str,
        skill_id: str,
        event_type: str,
        actor_open_id: str,
        skill_version: int | None,
        payload: dict[str, Any],
    ) -> None:
        cursor.execute(
            """
            insert into user_skill_audit_events
              (tenant_id, owner_open_id, skill_id, event_type, actor_open_id,
               skill_version, payload)
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                tenant_id,
                owner_open_id,
                skill_id,
                event_type,
                actor_open_id,
                skill_version,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _skill_select_sql() -> str:
        return """
            select s.id::text as id, s.tenant_id, s.owner_open_id, s.runtime_name,
                   s.latest_version, s.created_at, s.updated_at,
                   p.status, p.published_version,
                   v.id::text as version_id, v.version, v.display_name, v.description,
                   v.instructions_markdown, v.content_hash, v.created_by_open_id,
                   v.trigger_examples, v.non_trigger_examples, v.tags,
                   v.created_at as version_created_at
            from user_skills s
            join user_skill_publications p
              on p.tenant_id = s.tenant_id
             and p.owner_open_id = s.owner_open_id
             and p.skill_id = s.id
            join user_skill_versions v
              on v.tenant_id = s.tenant_id
             and v.owner_open_id = s.owner_open_id
             and v.skill_id = s.id
             and v.version = s.latest_version
        """

    @classmethod
    def _skill_from_row(cls, row: dict) -> UserSkill:
        version = UserSkillVersion(
            id=str(row["version_id"]),
            tenant_id=str(row["tenant_id"]),
            owner_open_id=str(row["owner_open_id"]),
            skill_id=str(row["id"]),
            version=int(row["version"]),
            display_name=str(row["display_name"]),
            description=str(row["description"]),
            instructions_markdown=str(row["instructions_markdown"]),
            trigger_examples=list(row["trigger_examples"] or []),
            non_trigger_examples=list(row["non_trigger_examples"] or []),
            tags=list(row["tags"] or []),
            content_hash=str(row["content_hash"]),
            created_by_open_id=str(row["created_by_open_id"]),
            created_at=row["version_created_at"],
        )
        return UserSkill(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            owner_open_id=str(row["owner_open_id"]),
            runtime_name=str(row["runtime_name"]),
            latest_version=int(row["latest_version"]),
            status=str(row["status"]),
            published_version=(
                int(row["published_version"]) if row["published_version"] is not None else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            latest_definition=version,
        )

    @staticmethod
    def _version_from_row(row: dict) -> UserSkillVersion:
        return UserSkillVersion(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            owner_open_id=str(row["owner_open_id"]),
            skill_id=str(row["skill_id"]),
            version=int(row["version"]),
            display_name=str(row["display_name"]),
            description=str(row["description"]),
            instructions_markdown=str(row["instructions_markdown"]),
            trigger_examples=list(row["trigger_examples"] or []),
            non_trigger_examples=list(row["non_trigger_examples"] or []),
            tags=list(row["tags"] or []),
            content_hash=str(row["content_hash"]),
            created_by_open_id=str(row["created_by_open_id"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _audit_from_row(row: dict) -> UserSkillAuditEvent:
        return UserSkillAuditEvent(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            owner_open_id=str(row["owner_open_id"]),
            skill_id=str(row["skill_id"]),
            event_type=str(row["event_type"]),
            actor_open_id=str(row["actor_open_id"]),
            skill_version=(int(row["skill_version"]) if row["skill_version"] is not None else None),
            payload=dict(row["payload"] or {}),
            created_at=row["created_at"],
        )

    @classmethod
    def _validate_definition(
        cls, display_name: str, description: str, instructions_markdown: str
    ) -> tuple[str, str, str]:
        display_name = cls._required_text(display_name, "display_name", cls.MAX_DISPLAY_NAME)
        description = cls._required_text(description, "description", cls.MAX_DESCRIPTION)
        instructions_markdown = cls._required_text(
            instructions_markdown, "instructions_markdown", cls.MAX_INSTRUCTIONS
        )
        if "\n" in description or "\r" in description:
            raise ValueError("description must be a single line")
        return display_name, description, instructions_markdown

    @staticmethod
    def _required_text(value: str, field: str, max_length: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} is required")
        if len(normalized) > max_length:
            raise ValueError(f"{field} exceeds {max_length} characters")
        return normalized

    @classmethod
    def _validate_identity(
        cls, tenant_id: str, owner_open_id: str, actor_open_id: str
    ) -> tuple[str, str, str]:
        return (
            cls._required_text(tenant_id, "tenant_id", 255),
            cls._required_text(owner_open_id, "owner_open_id", 255),
            cls._required_text(actor_open_id, "actor_open_id", 255),
        )

    @staticmethod
    def _validate_uuid(value: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise KeyError("Skill not found") from exc

    @staticmethod
    def _runtime_name(owner_open_id: str, skill_id: uuid.UUID) -> str:
        owner_hash = hashlib.sha256(owner_open_id.encode("utf-8")).hexdigest()[:10]
        return f"usr-{owner_hash}-{skill_id.hex[:16]}"

    @staticmethod
    def _name_key(display_name: str) -> str:
        normalized = unicodedata.normalize("NFKC", display_name).casefold()
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _content_hash(
        display_name: str,
        description: str,
        instructions_markdown: str,
        trigger_examples: list[str] | None = None,
        non_trigger_examples: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        canonical = json.dumps(
            {
                "display_name": display_name,
                "description": description,
                "instructions_markdown": instructions_markdown,
                "trigger_examples": list(trigger_examples or []),
                "non_trigger_examples": list(non_trigger_examples or []),
                "tags": list(tags or []),
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
