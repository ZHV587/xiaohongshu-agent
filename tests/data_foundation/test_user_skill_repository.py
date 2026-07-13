from __future__ import annotations

import psycopg
import pytest

from data_foundation.repositories.user_skill import UserSkillRepository


def _create(
    repo: UserSkillRepository,
    *,
    tenant_id: str = "tenant-a",
    owner_open_id: str = "ou-owner",
    display_name: str = "表达更犀利",
):
    return repo.create_skill(
        tenant_id=tenant_id,
        owner_open_id=owner_open_id,
        actor_open_id=owner_open_id,
        display_name=display_name,
        description="用户要求表达更直接、更有冲突感时使用",
        instructions_markdown="保留事实，只压缩铺垫并增强观点。",
    )


def test_definition_normalization_and_runtime_name_are_deterministic():
    assert UserSkillRepository._name_key("  ＡＢＣ　 文案  ") == "abc 文案"
    assert UserSkillRepository._name_key("AbC 文案") == "abc 文案"

    first = UserSkillRepository._content_hash("技能", "描述", "正文")
    second = UserSkillRepository._content_hash("技能", "描述", "正文")
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("display_name", " ", "display_name is required"),
        ("description", "第一行\n第二行", "description must be a single line"),
        ("instructions_markdown", " ", "instructions_markdown is required"),
    ],
)
def test_create_rejects_invalid_definition(migrated_conn, field, value, message):
    values = {
        "display_name": "技能",
        "description": "什么时候使用",
        "instructions_markdown": "具体规则",
    }
    values[field] = value
    repo = UserSkillRepository(migrated_conn)

    with pytest.raises(ValueError, match=message):
        repo.create_skill(
            tenant_id="tenant-a",
            owner_open_id="ou-owner",
            actor_open_id="ou-owner",
            **values,
        )


def test_create_and_append_keep_immutable_versions_without_bumping_catalog(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)

    assert skill.status == "draft"
    assert skill.latest_version == 1
    assert skill.published_version is None
    assert skill.runtime_name.startswith("usr-")
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 0

    changed = repo.append_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        display_name="表达更犀利",
        description="用户要求表达更直接、更有冲突感时使用",
        instructions_markdown="保留事实，删去铺垫，第一句直接给观点。",
        expected_latest_version=1,
    )

    assert changed.latest_version == 2
    assert changed.latest_definition.version == 2
    assert changed.latest_definition.instructions_markdown.endswith("第一句直接给观点。")
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 0
    rows = migrated_conn.execute(
        """
        select version, instructions_markdown
        from user_skill_versions
        where tenant_id = 'tenant-a' and owner_open_id = 'ou-owner' and skill_id = %s
        order by version
        """,
        (skill.id,),
    ).fetchall()
    assert [(row["version"], row["instructions_markdown"]) for row in rows] == [
        (1, "保留事实，只压缩铺垫并增强观点。"),
        (2, "保留事实，删去铺垫，第一句直接给观点。"),
    ]

    with pytest.raises(RuntimeError, match="version conflict"):
        repo.append_version(
            tenant_id="tenant-a",
            owner_open_id="ou-owner",
            actor_open_id="ou-owner",
            skill_id=skill.id,
            display_name="表达更犀利",
            description="用户要求表达更直接、更有冲突感时使用",
            instructions_markdown="第三版规则",
            expected_latest_version=1,
        )


def test_publish_disable_enable_rollback_archive_bump_revision_only_on_catalog_changes(
    migrated_conn,
):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)
    repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        version=1,
    )
    skill = repo.append_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        display_name="表达更犀利",
        description="用户要求表达更直接、更有冲突感时使用",
        instructions_markdown="第二版规则",
    )

    published = repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    assert (published.status, published.published_version) == ("published", 2)
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 2
    assert repo.get_published_version(
        tenant_id="tenant-a", owner_open_id="ou-owner", skill_id=skill.id
    ).version == 2

    # 幂等发布不会制造审计噪音，也不会让旧 thread 无故失效。
    repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        version=2,
    )
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 2

    disabled = repo.disable_skill(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    assert disabled.status == "disabled"
    assert repo.list_published_versions(tenant_id="tenant-a", owner_open_id="ou-owner") == []
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 3

    enabled = repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        version=2,
    )
    assert enabled.status == "published"
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 4

    rolled_back = repo.rollback_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
        version=1,
    )
    assert rolled_back.latest_version == 2
    assert rolled_back.published_version == 1
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 5

    archived = repo.archive_skill(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    assert archived.status == "archived"
    assert repo.list_skills(tenant_id="tenant-a", owner_open_id="ou-owner") == []
    assert len(
        repo.list_skills(
            tenant_id="tenant-a", owner_open_id="ou-owner", include_archived=True
        )
    ) == 1
    assert repo.get_catalog_revision(tenant_id="tenant-a", owner_open_id="ou-owner") == 6
    audit_events = repo.list_audit_events(
        tenant_id="tenant-a", owner_open_id="ou-owner", skill_id=skill.id
    )
    assert [event.event_type for event in audit_events] == [
        "archived",
        "rolled_back",
        "enabled",
        "disabled",
        "published",
        "version_created",
        "published",
        "created",
    ]
    # create 返回后的读取开启了 fixture 的长事务，之后七个事件共享同一个 now()；
    # 审计顺序必须由数据库生成的因果序号决定，不能退回随机 UUID 排序。
    assert len({event.created_at for event in audit_events[:-1]}) == 1
    assert [event.event_order for event in audit_events] == sorted(
        (event.event_order for event in audit_events), reverse=True
    )


def test_all_reads_are_tenant_and_owner_scoped(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)
    repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )

    for tenant_id, owner_open_id in [
        ("tenant-a", "ou-other"),
        ("tenant-b", "ou-owner"),
    ]:
        with pytest.raises(KeyError, match="Skill not found"):
            repo.get_skill(
                tenant_id=tenant_id, owner_open_id=owner_open_id, skill_id=skill.id
            )
        with pytest.raises(KeyError, match="Published skill not found"):
            repo.get_published_version(
                tenant_id=tenant_id, owner_open_id=owner_open_id, skill_id=skill.id
            )
        assert repo.list_skills(tenant_id=tenant_id, owner_open_id=owner_open_id) == []
        assert repo.list_published_versions(
            tenant_id=tenant_id, owner_open_id=owner_open_id
        ) == []
        assert repo.list_audit_events(
            tenant_id=tenant_id, owner_open_id=owner_open_id, skill_id=skill.id
        ) == []
        assert repo.get_catalog_revision(
            tenant_id=tenant_id, owner_open_id=owner_open_id
        ) == 0


def test_runtime_document_batch_returns_only_current_owner_published_versions(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    published = _create(repo, display_name="已发布流程")
    draft = _create(repo, display_name="草稿流程")
    repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=published.id,
    )

    documents = repo.list_published_documents(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
    )
    assert [(item.runtime_name, item.version) for item in documents] == [
        (published.runtime_name, 1)
    ]
    assert documents[0].description == published.latest_definition.description
    assert draft.runtime_name not in {item.runtime_name for item in documents}
    assert repo.list_published_documents(
        tenant_id="tenant-a",
        owner_open_id="ou-other",
    ) == []

    registry = repo.list_published_registry_entries(
        tenant_id="tenant-a", owner_open_id="ou-owner"
    )
    assert [(item.skill_id, item.version_id, item.runtime_name) for item in registry] == [
        (published.id, published.latest_definition.id, published.runtime_name)
    ]
    assert registry[0].tags == published.latest_definition.tags
    assert not hasattr(registry[0], "instructions_markdown")
    assert repo.list_published_registry_entries(
        tenant_id="tenant-a", owner_open_id="ou-other"
    ) == []


def test_selected_document_modes_enforce_current_publication_and_owner(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo, display_name="精确执行流程")
    draft_version_id = skill.latest_definition.id

    tested = repo.resolve_selected_document(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        skill_id=skill.id,
        version_id=draft_version_id,
        mode="test",
    )
    assert tested.definition.id == draft_version_id
    with pytest.raises(KeyError, match="Selected Skill not found"):
        repo.resolve_selected_document(
            tenant_id="tenant-a",
            owner_open_id="ou-owner",
            skill_id=skill.id,
            version_id=draft_version_id,
            mode="execute",
        )

    published = repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    executed = repo.resolve_selected_document(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        skill_id=skill.id,
        version_id=draft_version_id,
        mode="execute",
    )
    assert executed.published_version == published.published_version

    repo.disable_skill(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    with pytest.raises(KeyError, match="Selected Skill not found"):
        repo.resolve_selected_document(
            tenant_id="tenant-a",
            owner_open_id="ou-owner",
            skill_id=skill.id,
            version_id=draft_version_id,
            mode="execute",
        )
    assert repo.resolve_selected_document(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        skill_id=skill.id,
        version_id=draft_version_id,
        mode="test",
    ).status == "disabled"

    with pytest.raises(KeyError, match="Selected Skill not found"):
        repo.resolve_selected_document(
            tenant_id="tenant-a",
            owner_open_id="ou-other",
            skill_id=skill.id,
            version_id=draft_version_id,
            mode="test",
        )


def test_rollback_accepts_only_previously_published_version_and_preserves_disabled(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)
    repo.publish_version(
        tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
        skill_id=skill.id, version=1,
    )
    repo.append_version(
        tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
        skill_id=skill.id, display_name="表达更犀利",
        description="用户要求表达更直接、更有冲突感时使用",
        instructions_markdown="从未发布的第二版",
    )
    with pytest.raises(ValueError, match="never published"):
        repo.rollback_version(
            tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
            skill_id=skill.id, version=2,
        )

    repo.publish_version(
        tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
        skill_id=skill.id, version=2,
    )
    repo.disable_skill(
        tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
        skill_id=skill.id,
    )
    rolled_back = repo.rollback_version(
        tenant_id="tenant-a", owner_open_id="ou-owner", actor_open_id="ou-owner",
        skill_id=skill.id, version=1,
    )
    assert rolled_back.status == "disabled"
    assert rolled_back.published_version == 1


def test_normalized_name_is_unique_per_owner_until_archived(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    first = _create(repo, display_name="ＡＢＣ　 文案")

    with pytest.raises(psycopg.errors.UniqueViolation):
        _create(repo, display_name="abc 文案")

    # 另一用户拥有独立命名空间。
    other = _create(repo, owner_open_id="ou-other", display_name="abc 文案")
    assert other.owner_open_id == "ou-other"

    repo.archive_skill(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=first.id,
    )
    replacement = _create(repo, display_name="abc 文案")
    assert replacement.id != first.id


def test_database_rejects_version_and_audit_mutation_and_hard_delete(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)
    version_id = skill.latest_definition.id
    audit_id = repo.list_audit_events(
        tenant_id="tenant-a", owner_open_id="ou-owner", skill_id=skill.id
    )[0].id

    for statement, params in [
        ("update user_skill_versions set display_name='篡改' where id=%s", (version_id,)),
        ("delete from user_skill_versions where id=%s", (version_id,)),
        ("update user_skill_audit_events set event_type='篡改' where id=%s", (audit_id,)),
        ("delete from user_skill_audit_events where id=%s", (audit_id,)),
        ("delete from user_skills where id=%s", (skill.id,)),
    ]:
        with pytest.raises(psycopg.DatabaseError):
            with migrated_conn.transaction():
                migrated_conn.execute(statement, params)

    assert repo.get_skill(
        tenant_id="tenant-a", owner_open_id="ou-owner", skill_id=skill.id
    ).latest_definition.display_name == "表达更犀利"
    assert repo.list_audit_events(
        tenant_id="tenant-a", owner_open_id="ou-owner", skill_id=skill.id
    )[0].event_type == "created"


def test_publication_pointer_cannot_cross_skill_or_owner(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    first = _create(repo, display_name="技能一")
    second = _create(repo, display_name="技能二")
    repo.append_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=second.id,
        display_name="技能二",
        description="用户需要技能二时使用",
        instructions_markdown="第二版",
    )

    # second 有 v2，但 first 没有；复合外键必须拒绝把 first 指向 second 的版本号。
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with migrated_conn.transaction():
            migrated_conn.execute(
                """
                update user_skill_publications
                set status = 'published', published_version = 2
                where tenant_id = 'tenant-a' and owner_open_id = 'ou-owner' and skill_id = %s
                """,
                (first.id,),
            )


def test_skill_storage_never_creates_content_resources_or_index_work(migrated_conn):
    repo = UserSkillRepository(migrated_conn)
    skill = _create(repo)
    repo.publish_version(
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        actor_open_id="ou-owner",
        skill_id=skill.id,
    )

    assert migrated_conn.execute("select count(*) as count from resources").fetchone()["count"] == 0
    assert migrated_conn.execute("select count(*) as count from resource_outbox").fetchone()["count"] == 0
