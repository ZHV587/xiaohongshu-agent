from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from psycopg.rows import dict_row

from data_foundation.outbox_requests import default_write_requests


class GeneratedCopyConflict(RuntimeError):
    """文案版本或生命周期状态已被另一写操作推进。"""


@dataclass(frozen=True)
class GeneratedCopyState:
    resource_id: str
    lifecycle_status: str
    selected_version: int | None
    selected_label: str | None
    adopted_version: int | None
    finalized_version: int | None
    published_version: int | None
    knowledge_target_version: int | None
    latest_resource_version: int
    state_version: int
    finalize_request_id: str | None = None
    finalize_draft_hash: str | None = None
    finalize_base_version: int | None = None

    def payload(self) -> dict[str, Any]:
        return asdict(self)


class GeneratedCopyRepository:
    """generated_copy 单资源、多不可变版本生命周期仓储。

    所有修改都先 `FOR UPDATE` 锁定 generated_copy_states，再校验 state_version；因此
    ResourceRepository 追加版本时不会出现两个并发请求计算出相同 next_version 的竞态。
    """

    def __init__(self, resource_repo: Any):
        if getattr(resource_repo, "conn", None) is None:
            raise RuntimeError("GeneratedCopyRepository requires a connection-bound ResourceRepository")
        self.resource_repo = resource_repo
        self.conn = resource_repo.conn

    def initialize_candidate(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        label: str | None = None,
        candidates: list[dict[str, Any]] | None = None,
        origin_turn_id: str | None = None,
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            self._assert_version(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource_id,
                resource_version=resource_version,
            )
            selected_label = self._label(label) or self._version_label(
                tenant_id=tenant_id, resource_id=resource_id, resource_version=resource_version
            ) or f"V{resource_version}"
            normalized_candidates = candidates or [
                {"version": resource_version, "label": self._label(label)}
            ]
            inserted = self.conn.execute(
                """
                insert into generated_copy_states (
                  tenant_id, resource_id, owner_open_id, origin_turn_id,
                  lifecycle_status, selected_version, selected_label, state_version, updated_by_open_id
                ) values (%s, %s, %s, %s, 'candidate', %s, %s, 1, %s)
                on conflict (tenant_id, resource_id) do nothing
                returning resource_id
                """,
                (
                    tenant_id,
                    resource_id,
                    actor_open_id,
                    self._origin(origin_turn_id),
                    resource_version,
                    selected_label,
                    actor_open_id,
                ),
            ).fetchone()
            if inserted is not None:
                self._event(
                    tenant_id=tenant_id,
                    resource_id=resource_id,
                    actor_open_id=actor_open_id,
                    event_type="candidates_created",
                    payload={"candidates": normalized_candidates},
                )
            return self._locked_state(tenant_id=tenant_id, resource_id=resource_id)

    def lock_origin(
        self, *, tenant_id: str, actor_open_id: str, origin_turn_id: str
    ) -> None:
        origin = self._origin(origin_turn_id)
        if origin is None:
            raise ValueError("origin_turn_id is required")
        # 同一租户/用户/生成轮次串行化，避免工具重试并发创建两个 resource 后才撞唯一键。
        self.conn.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"generated-copy:{tenant_id}:{actor_open_id}:{origin}",),
        )

    def find_by_origin(
        self, *, tenant_id: str, actor_open_id: str, origin_turn_id: str
    ) -> dict[str, Any] | None:
        origin = self._origin(origin_turn_id)
        if origin is None:
            return None
        state = self.conn.execute(
            """
            select s.*,
                   (select max(rv.version) from resource_versions rv
                    where rv.tenant_id = s.tenant_id and rv.resource_id = s.resource_id)
                     as latest_resource_version
            from generated_copy_states s
            where s.tenant_id = %s and s.owner_open_id = %s and s.origin_turn_id = %s
            """,
            (tenant_id, actor_open_id, origin),
        ).fetchone()
        if state is None:
            return None
        created = self.conn.execute(
            """
            select payload
            from resource_events
            where tenant_id = %s and resource_id = %s and event_type = 'candidates_created'
            order by created_at, id
            limit 1
            """,
            (tenant_id, state["resource_id"]),
        ).fetchone()
        original_candidates = list(dict(created["payload"] or {}).get("candidates") or []) if created else []
        original_versions = [
            int(item.get("resource_version"))
            for item in original_candidates
            if isinstance(item, dict) and isinstance(item.get("resource_version"), int)
        ]
        if not original_versions:
            original_versions = [int(state["selected_version"])]
        rows = self.conn.execute(
            """
            select rv.version, rv.content_json
            from resource_versions rv
            where rv.tenant_id = %s and rv.resource_id = %s and rv.version = any(%s)
            """,
            (tenant_id, state["resource_id"], original_versions),
        ).fetchall()
        by_version = {int(row["version"]): row for row in rows}
        rows = [by_version[version] for version in original_versions if version in by_version]
        versions = [
            {
                "label": dict(row["content_json"] or {}).get("variant_label"),
                "resource_version": int(row["version"]),
                "title": dict(row["content_json"] or {}).get("title") or "",
            }
            for row in rows
        ]
        return {
            "ok": True,
            "resource": {
                "resource_id": str(state["resource_id"]),
                "type": "generated_copy",
                "title": versions[0]["title"] if versions else "",
                "resource_version": int(original_versions[0]),
                "latest_resource_version": int(state["latest_resource_version"]),
                "state_version": int(state["state_version"]),
                "versions": versions,
            },
            "evidence_count": 0,
            "idempotent_replay": True,
        }

    def get_state(
        self, *, tenant_id: str, actor_open_id: str, resource_id: str
    ) -> GeneratedCopyState:
        self.resource_repo.writable_resource_metadata(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=resource_id,
        )
        with self.conn.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute(self._STATE_SQL, (tenant_id, resource_id)).fetchone()
        if row is None:
            raise ValueError("generated copy lifecycle is not initialized")
        return self._state(row)

    def list_versions(
        self, *, tenant_id: str, actor_open_id: str, resource_id: str
    ) -> list[dict[str, Any]]:
        """Return every immutable generated-copy snapshot in ascending order.

        Lifecycle restore must never rebuild candidate cards from ``resources`` because
        that row only contains the latest body.  Each card is hydrated exclusively from
        its ``resource_versions`` snapshot after a write-ACL check.
        """
        meta = self.resource_repo.writable_resource_metadata(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=resource_id,
        )
        if meta.get("type") not in (None, "generated_copy"):
            raise ValueError("resource is not a generated_copy")
        rows = self.conn.execute(
            """
            select version, content_json
            from resource_versions
            where tenant_id = %s and resource_id = %s
            order by version
            """,
            (tenant_id, resource_id),
        ).fetchall()
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            version = int(row["version"])
            content = dict(row["content_json"] or {})
            raw_tags = content.get("tags")
            tags = (
                [tag for tag in raw_tags if isinstance(tag, str)]
                if isinstance(raw_tags, list)
                else []
            )
            snapshots.append(
                {
                    "resourceVersion": version,
                    "label": self._label(content.get("variant_label")) or f"V{version}",
                    "title": content.get("title") if isinstance(content.get("title"), str) else "",
                    "body": content.get("body") if isinstance(content.get("body"), str) else "",
                    "tags": tags,
                    "cover": content.get("cover") if isinstance(content.get("cover"), str) else "",
                    "note": content.get("note") if isinstance(content.get("note"), str) else "",
                }
            )
        return snapshots

    def select_version(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        expected_state_version: int,
        label: str | None = None,
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            self._expect_state(current, expected_state_version)
            self._ensure_mutable(current, action="select")
            self._assert_version(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource_id,
                resource_version=resource_version,
            )
            snapshot_label = self._version_label(
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_version=resource_version,
            ) or f"V{resource_version}"
            requested_label = self._label(label)
            if requested_label is not None and requested_label != snapshot_label:
                raise ValueError("label does not match the selected resource version")
            selected_label = snapshot_label
            row = self.conn.execute(
                """
                update generated_copy_states
                set selected_version = %s,
                    selected_label = %s,
                    lifecycle_status = 'selected',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (
                    resource_version,
                    selected_label,
                    actor_open_id,
                    tenant_id,
                    resource_id,
                ),
            ).fetchone()
            self._event(
                tenant_id=tenant_id,
                resource_id=resource_id,
                actor_open_id=actor_open_id,
                event_type="variant_selected",
                payload={"version": resource_version, "label": selected_label},
            )
            return self._state_with_latest(row)

    def save_revision(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        expected_resource_version: int,
        expected_state_version: int,
        title: str,
        body: str,
        tags: list[str],
        label: str | None = None,
        cover: str | None = None,
        note: str | None = None,
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            self._expect_state(current, expected_state_version)
            self._ensure_mutable(current, action="revise")
            if (
                not isinstance(expected_resource_version, int)
                or isinstance(expected_resource_version, bool)
                or expected_resource_version <= 0
            ):
                raise ValueError("expected_resource_version must be a positive integer")
            if current.latest_resource_version != expected_resource_version:
                raise GeneratedCopyConflict(
                    f"resource version changed: expected {expected_resource_version}, "
                    f"current {current.latest_resource_version}"
                )
            revision_label = self._label(label) or current.selected_label
            if revision_label is None:
                base_version = current.selected_version or current.latest_resource_version
                revision_label = self._version_label(
                    tenant_id=tenant_id,
                    resource_id=resource_id,
                    resource_version=base_version,
                ) or f"V{base_version}"
            base_version = current.selected_version or current.latest_resource_version
            saved = self._append_revision(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource_id,
                base_resource_version=base_version,
                title=title,
                body=body,
                tags=tags,
                label=revision_label,
                cover=cover,
                note=note,
            )
            row = self.conn.execute(
                """
                update generated_copy_states
                set selected_version = %s,
                    selected_label = %s,
                    lifecycle_status = 'selected',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (
                    saved.version,
                    revision_label,
                    actor_open_id,
                    tenant_id,
                    resource_id,
                ),
            ).fetchone()
            self._event(
                tenant_id=tenant_id,
                resource_id=resource_id,
                actor_open_id=actor_open_id,
                event_type="revision_saved",
                payload={"version": saved.version, "base_version": base_version},
            )
            return self._state(row, latest_resource_version=int(saved.version))

    def adopt_version(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        expected_state_version: int,
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            self._expect_state(current, expected_state_version)
            self._ensure_mutable(current, action="adopt")
            self._assert_version(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource_id,
                resource_version=resource_version,
            )
            selected_label = self._version_label(
                tenant_id=tenant_id, resource_id=resource_id, resource_version=resource_version
            ) or f"V{resource_version}"
            row = self.conn.execute(
                """
                update generated_copy_states
                set selected_version = %s,
                    selected_label = %s,
                    adopted_version = %s,
                    knowledge_target_version = %s,
                    lifecycle_status = 'adopted',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (
                    resource_version,
                    selected_label,
                    resource_version,
                    resource_version,
                    actor_open_id,
                    tenant_id,
                    resource_id,
                ),
            ).fetchone()
            self._event_and_index(
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_version=resource_version,
                actor_open_id=actor_open_id,
                event_type="adopted",
                payload={"version": resource_version},
            )
            return self._state_with_latest(row)

    def finalize_for_schedule(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        target_resource_version: int,
        expected_latest_resource_version: int,
        expected_state_version: int,
        final_draft: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> GeneratedCopyState:
        """把排期所用的精确快照原子地采纳并定稿。

        若请求携带 final_draft，先校验 base resource_version 后追加一个不可变修订版本，
        再把 selected/adopted/finalized 三个指针一次性指向新版本。
        """
        normalized_request_id = self._idempotency_key(request_id)
        normalized_draft: dict[str, Any] | None = None
        draft_hash: str | None = None
        if final_draft is not None:
            if normalized_request_id is None:
                raise ValueError("request_id is required when final_draft is provided")
            normalized_draft = self._normalize_revision_payload(final_draft)
            draft_hash = hashlib.sha256(
                json.dumps(
                    normalized_draft, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
        for field, value in (
            ("target_resource_version", target_resource_version),
            ("expected_latest_resource_version", expected_latest_resource_version),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            # A response may be lost after commit.  Resolve the exact finalized retry
            # before checking the now-stale CAS token, otherwise clients either get a
            # false 409 or append the same final draft twice.
            if normalized_draft is not None and current.finalize_request_id == normalized_request_id:
                if (
                    current.finalize_draft_hash != draft_hash
                    or current.finalize_base_version != target_resource_version
                    or current.finalized_version is None
                ):
                    raise GeneratedCopyConflict(
                        "finalization request id was reused with a different draft"
                    )
                return current
            if current.lifecycle_status in {"finalized", "published", "measured"}:
                if normalized_draft is not None or current.finalized_version != target_resource_version:
                    raise GeneratedCopyConflict(
                        "a finalized or published copy cannot be replaced by rescheduling"
                    )
                return current
            self._expect_state(current, expected_state_version)
            if current.latest_resource_version != expected_latest_resource_version:
                raise GeneratedCopyConflict(
                    "latest resource version changed: "
                    f"expected {expected_latest_resource_version}, "
                    f"current {current.latest_resource_version}"
                )
            if current.selected_version != target_resource_version:
                raise GeneratedCopyConflict(
                    f"schedule version must match selected_version {current.selected_version}"
                )
            final_version = target_resource_version
            if normalized_draft is not None:
                saved = self._append_revision(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_id=resource_id,
                    base_resource_version=target_resource_version,
                    title=normalized_draft["title"],
                    body=normalized_draft["body"],
                    tags=normalized_draft["tags"],
                    # A schedule-time dirty save is a new immutable revision of the
                    # selected slot, not a fourth UI variant.  Preserve A/B/C (or the
                    # custom selected label); the event records finalization semantics.
                    label=current.selected_label
                    or self._version_label(
                        tenant_id=tenant_id,
                        resource_id=resource_id,
                        resource_version=target_resource_version,
                    ),
                    cover=normalized_draft["cover"],
                    note=normalized_draft["note"],
                )
                final_version = int(saved.version)
                self._event(
                    tenant_id=tenant_id,
                    resource_id=resource_id,
                    actor_open_id=actor_open_id,
                    event_type="revision_saved",
                    payload={"version": final_version, "base_version": target_resource_version},
                )
            else:
                self._assert_version(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_id=resource_id,
                    resource_version=target_resource_version,
                )
            row = self.conn.execute(
                """
                update generated_copy_states
                set selected_version = %s,
                    selected_label = %s,
                    adopted_version = %s,
                    finalized_version = %s,
                    knowledge_target_version = %s,
                    finalize_request_id = %s,
                    finalize_draft_hash = %s,
                    finalize_base_version = %s,
                    lifecycle_status = 'finalized',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (
                    final_version,
                    self._version_label(
                        tenant_id=tenant_id,
                        resource_id=resource_id,
                        resource_version=final_version,
                    ) or f"V{final_version}",
                    final_version,
                    final_version,
                    final_version,
                    normalized_request_id,
                    draft_hash,
                    target_resource_version if normalized_draft is not None else None,
                    actor_open_id,
                    tenant_id,
                    resource_id,
                ),
            ).fetchone()
            self._event_and_index(
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_version=final_version,
                actor_open_id=actor_open_id,
                event_type="finalized_for_schedule",
                payload={
                    "version": final_version,
                    "base_version": target_resource_version,
                    "expected_latest_version": expected_latest_resource_version,
                    "implicitly_adopted": True,
                    "request_id": normalized_request_id,
                    "draft_hash": draft_hash,
                },
            )
            return self._state(row, latest_resource_version=max(current.latest_resource_version, final_version))

    def mark_published(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            if current.lifecycle_status in {"published", "measured"}:
                return current
            if current.finalized_version is None:
                raise GeneratedCopyConflict("copy must be finalized before publishing")
            row = self.conn.execute(
                """
                update generated_copy_states
                set published_version = finalized_version,
                    lifecycle_status = 'published',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (actor_open_id, tenant_id, resource_id),
            ).fetchone()
            self._event(
                tenant_id=tenant_id,
                resource_id=resource_id,
                actor_open_id=actor_open_id,
                event_type="published",
                payload={"version": current.finalized_version},
            )
            return self._state(row, latest_resource_version=current.latest_resource_version)

    def attributable_version(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        requested_version: int | None = None,
    ) -> int:
        current = self.get_state(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
        )
        if current.published_version is None:
            raise GeneratedCopyConflict("performance requires an exactly published copy version")
        version = requested_version or current.published_version
        if version != current.published_version:
            raise GeneratedCopyConflict("performance version must match published_version exactly")
        return int(version)

    def mark_measured(
        self, *, tenant_id: str, actor_open_id: str, resource_id: str
    ) -> GeneratedCopyState:
        with self.conn.transaction():
            current = self._lock_and_authorize(
                tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
            )
            if current.lifecycle_status == "measured":
                return current
            if current.published_version is None:
                raise GeneratedCopyConflict("copy must be published before metrics are recorded")
            row = self.conn.execute(
                """
                update generated_copy_states
                set lifecycle_status = 'measured',
                    state_version = state_version + 1,
                    updated_by_open_id = %s,
                    updated_at = now()
                where tenant_id = %s and resource_id = %s
                returning *
                """,
                (actor_open_id, tenant_id, resource_id),
            ).fetchone()
            self._event(
                tenant_id=tenant_id,
                resource_id=resource_id,
                actor_open_id=actor_open_id,
                event_type="metrics_backfilled",
                payload={"version": current.published_version},
            )
            return self._state(row, latest_resource_version=current.latest_resource_version)

    def _append_revision(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        base_resource_version: int,
        title: Any,
        body: Any,
        tags: Any,
        label: str | None,
        cover: str | None = None,
        note: str | None = None,
    ):
        title = title.strip() if isinstance(title, str) else ""
        body = body.strip() if isinstance(body, str) else ""
        if not title or not body:
            raise ValueError("title and body are required")
        if not isinstance(tags, list):
            raise ValueError("tags must be an array")
        cleaned_tags = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]
        existing = self.resource_repo.get_resource_version(
            tenant_id,
            actor_open_id,
            resource_id,
            base_resource_version,
        )
        if existing is None or existing.type != "generated_copy":
            raise ValueError("resource is not a generated_copy")
        content_json = dict(existing.content_json or {})
        content_json.update(
            {
                "title": title,
                "body": body,
                "tags": cleaned_tags,
                "variant_label": self._label(label),
            }
        )
        if isinstance(cover, str):
            content_json["cover"] = cover.strip()
        if isinstance(note, str):
            content_json["note"] = note.strip()
        text = "\n".join([title, "", body, "", " ".join(cleaned_tags)]).rstrip()
        return self.resource_repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=resource_id,
            resource_type="generated_copy",
            title=title,
            summary=existing.summary,
            content_text=text,
            content_json=content_json,
            status=existing.status,
            visibility=existing.visibility,
            owner_open_id=existing.owner_open_id,
            outbox_requests=[],
        )

    def _lock_and_authorize(
        self, *, tenant_id: str, actor_open_id: str, resource_id: str
    ) -> GeneratedCopyState:
        self.resource_repo.writable_resource_metadata(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
        )
        row = self.conn.execute(
            self._STATE_SQL + " for update", (tenant_id, resource_id)
        ).fetchone()
        if row is None:
            raise ValueError("generated copy lifecycle is not initialized")
        return self._state(row)

    def _locked_state(self, *, tenant_id: str, resource_id: str) -> GeneratedCopyState:
        row = self.conn.execute(
            self._STATE_SQL + " for update", (tenant_id, resource_id)
        ).fetchone()
        if row is None:
            raise ValueError("generated copy lifecycle is not initialized")
        return self._state(row)

    def _assert_version(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
    ) -> None:
        if not isinstance(resource_version, int) or isinstance(resource_version, bool) or resource_version <= 0:
            raise ValueError("resource_version must be a positive integer")
        meta = self.resource_repo.writable_resource_metadata(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
        )
        if meta.get("type") not in (None, "generated_copy"):
            raise ValueError("resource is not a generated_copy")
        row = self.conn.execute(
            """
            select 1 from resource_versions
            where tenant_id = %s and resource_id = %s and version = %s
            """,
            (tenant_id, resource_id, resource_version),
        ).fetchone()
        if row is None:
            raise ValueError("resource version does not exist")

    @staticmethod
    def _expect_state(current: GeneratedCopyState, expected: int) -> None:
        if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
            raise ValueError("expected_state_version must be a positive integer")
        if current.state_version != expected:
            raise GeneratedCopyConflict(
                f"state version changed: expected {expected}, current {current.state_version}"
            )

    @staticmethod
    def _ensure_mutable(current: GeneratedCopyState, *, action: str) -> None:
        if current.lifecycle_status in {"finalized", "published", "measured"}:
            raise GeneratedCopyConflict(
                f"cannot {action} a {current.lifecycle_status} copy"
            )

    def _event_and_index(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        actor_open_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event_id = self._event(
            tenant_id=tenant_id,
            resource_id=resource_id,
            actor_open_id=actor_open_id,
            event_type=event_type,
            payload=payload,
        )
        self.resource_repo._enqueue_outbox(
            tenant_id=tenant_id,
            resource_id=resource_id,
            version=resource_version,
            requests=default_write_requests(),
            event_id=event_id,
            dedupe_event=True,
            cursor=self.conn,
        )

    def _version_label(
        self, *, tenant_id: str, resource_id: str, resource_version: int
    ) -> str | None:
        row = self.conn.execute(
            """
            select content_json->>'variant_label' as label
            from resource_versions
            where tenant_id = %s and resource_id = %s and version = %s
            """,
            (tenant_id, resource_id, resource_version),
        ).fetchone()
        return None if row is None else self._label(row["label"])

    def _event(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        actor_open_id: str,
        event_type: str,
        payload: dict[str, Any],
    ):
        row = self.conn.execute(
            """
            insert into resource_events (tenant_id, resource_id, event_type, actor_open_id, payload)
            values (%s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                tenant_id,
                resource_id,
                event_type,
                actor_open_id,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        return row["id"]

    def _state_with_latest(self, row: Any) -> GeneratedCopyState:
        latest = self.conn.execute(
            "select max(version) as version from resource_versions where resource_id = %s",
            (row["resource_id"],),
        ).fetchone()
        return self._state(row, latest_resource_version=int(latest["version"]))

    @staticmethod
    def _state(row: Any, latest_resource_version: int | None = None) -> GeneratedCopyState:
        return GeneratedCopyState(
            resource_id=str(row["resource_id"]),
            lifecycle_status=row["lifecycle_status"],
            selected_version=None if row["selected_version"] is None else int(row["selected_version"]),
            selected_label=row["selected_label"],
            adopted_version=None if row["adopted_version"] is None else int(row["adopted_version"]),
            finalized_version=None if row["finalized_version"] is None else int(row["finalized_version"]),
            published_version=None if row["published_version"] is None else int(row["published_version"]),
            knowledge_target_version=(
                None
                if row["knowledge_target_version"] is None
                else int(row["knowledge_target_version"])
            ),
            latest_resource_version=int(
                latest_resource_version if latest_resource_version is not None else row["latest_resource_version"]
            ),
            state_version=int(row["state_version"]),
            finalize_request_id=row.get("finalize_request_id"),
            finalize_draft_hash=row.get("finalize_draft_hash"),
            finalize_base_version=(
                None
                if row.get("finalize_base_version") is None
                else int(row["finalize_base_version"])
            ),
        )

    @staticmethod
    def _label(value: str | None) -> str | None:
        cleaned = value.strip() if isinstance(value, str) else ""
        return cleaned[:80] or None

    @staticmethod
    def _origin(value: str | None) -> str | None:
        cleaned = value.strip() if isinstance(value, str) else ""
        return cleaned[:200] or None

    @staticmethod
    def _idempotency_key(value: str | None) -> str | None:
        cleaned = value.strip() if isinstance(value, str) else ""
        return cleaned[:200] or None

    @staticmethod
    def _normalize_revision_payload(payload: dict[str, Any]) -> dict[str, Any]:
        title = payload.get("title")
        body = payload.get("body")
        tags = payload.get("tags")
        title = title.strip() if isinstance(title, str) else ""
        body = body.strip() if isinstance(body, str) else ""
        if not title or not body:
            raise ValueError("final_draft title and body are required")
        if not isinstance(tags, list):
            raise ValueError("final_draft tags must be an array")
        return {
            "title": title,
            "body": body,
            "tags": [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()],
            "cover": payload.get("cover").strip() if isinstance(payload.get("cover"), str) else "",
            "note": payload.get("note").strip() if isinstance(payload.get("note"), str) else "",
        }

    _STATE_SQL = """
        select s.*,
               (select max(rv.version) from resource_versions rv
                where rv.tenant_id = s.tenant_id and rv.resource_id = s.resource_id)
                 as latest_resource_version
        from generated_copy_states s
        where s.tenant_id = %s and s.resource_id = %s
    """


__all__ = [
    "GeneratedCopyConflict",
    "GeneratedCopyRepository",
    "GeneratedCopyState",
]
