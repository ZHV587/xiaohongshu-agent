from langchain_core.messages import AIMessage
import pytest

from data_foundation.generation_provenance import latest_model_provenance
from data_foundation.repositories.account import AccountRepository
from data_foundation.repositories.generation import GenerationRepository
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.writing_context import WritingContext


def test_latest_model_provenance_uses_actual_success_metadata_only() -> None:
    messages = [
        AIMessage(content="旧结果"),
        AIMessage(
            content="成功结果",
            response_metadata={
                "xhs_model_provider": "anthropic",
                "xhs_model_id": "quality-model",
                "xhs_gateway_name": "gateway-2",
            },
        ),
    ]
    assert latest_model_provenance(messages) == {
        "provider": "anthropic",
        "model_id": "quality-model",
        "gateway_name": "gateway-2",
    }


def test_account_platform_identity_upsert_is_stable_and_owner_scoped(migrated_conn) -> None:
    accounts = AccountRepository(migrated_conn)
    first = accounts.upsert_account(
        tenant_id="default",
        actor_open_id="ou-owner",
        display_name="露营号",
        platform_account_id="xhs-001",
        niche="露营",
    )
    replay = accounts.upsert_account(
        tenant_id="default",
        actor_open_id="ou-owner",
        display_name="露营主号",
        platform_account_id="xhs-001",
        niche="户外露营",
    )
    assert str(replay["id"]) == str(first["id"])
    assert replay["display_name"] == "露营主号"

    with pytest.raises(ValueError, match="another account"):
        accounts.upsert_account(
            tenant_id="default",
            actor_open_id="ou-owner",
            account_id="33333333-3333-4333-8333-333333333333",
            display_name="冲突号",
            platform_account_id="xhs-001",
        )

    other = accounts.upsert_account(
        tenant_id="default",
        actor_open_id="ou-other",
        display_name="他人账号",
        platform_account_id="xhs-other",
    )
    with pytest.raises(PermissionError, match="not owned"):
        accounts.upsert_account(
            tenant_id="default",
            actor_open_id="ou-owner",
            account_id=str(other["id"]),
            display_name="越权更新",
        )

    probe = ResourceRepository(migrated_conn).upsert_resource(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_type="document",
        title="账号过滤探针",
        content_text="仅用于验证账号过滤权限",
        content_json={},
        visibility="team",
        owner_open_id="ou-owner",
        outbox_requests=[],
    )
    with pytest.raises(PermissionError, match="account filter"):
        ResourceRepository(migrated_conn).current_knowledge_rows(
            tenant_id="default",
            actor_open_id="ou-owner",
            resource_ids=[str(probe.id)],
            resource_versions=[int(probe.version)],
            account_ids=[str(other["id"])],
        )


def test_generation_selection_uses_latest_presented_run_and_is_idempotent(migrated_conn) -> None:
    resources = ResourceRepository(migrated_conn)
    versions = []
    resource_id = None
    for label in ("A", "B", "C"):
        saved = resources.upsert_resource(
            tenant_id="default",
            actor_open_id="ou-owner",
            resource_id=resource_id,
            resource_type="generated_copy",
            title=f"版本 {label}",
            content_text=f"正文 {label}",
            content_json={"title": f"版本 {label}", "body": f"正文 {label}", "tags": []},
            visibility="team",
            owner_open_id="ou-owner",
            outbox_requests=[],
        )
        resource_id = str(saved.id)
        versions.append({"label": label, "resource_version": int(saved.version)})

    generations = GenerationRepository(migrated_conn)
    first_run = generations.record_generation(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=resource_id,
        variants=versions,
        run_id="run-1",
        turn_id="turn-1",
        thread_id="thread-1",
        task_type="copywriting",
        request_digest="a" * 64,
        prompt_contract_version="contract-v1",
        model={"provider": "openai", "model_id": "m1", "gateway_name": "g1"},
        knowledge_grounding={"schema_version": 1, "evidence": []},
        profile=None,
        user_skill=None,
        writing_context=WritingContext(),
    )
    second_run = generations.record_generation(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=resource_id,
        variants=versions[:2],
        run_id="run-2",
        turn_id="turn-2",
        thread_id="thread-1",
        task_type="revision",
        request_digest="b" * 64,
        prompt_contract_version="contract-v1",
        model={"provider": "openai", "model_id": "m2", "gateway_name": "g2"},
        knowledge_grounding={"schema_version": 1, "evidence": []},
        profile=None,
        user_skill=None,
        writing_context=WritingContext(),
    )
    assert first_run != second_run
    event_id = str(
        migrated_conn.execute(
            """
            insert into resource_events (tenant_id, resource_id, event_type, actor_open_id)
            values ('default', %s, 'adopted', 'ou-owner')
            returning id::text
            """,
            (resource_id,),
        ).fetchone()["id"]
    )
    comparisons = generations.record_selection(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=resource_id,
        resource_version=versions[1]["resource_version"],
        selection_event_id=event_id,
    )
    assert len(comparisons) == 1
    assert comparisons[0]["generation_run_id"] == second_run
    assert comparisons[0]["rejected_resource_version"] == versions[0]["resource_version"]
    assert generations.record_selection(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=resource_id,
        resource_version=versions[1]["resource_version"],
        selection_event_id=event_id,
    ) == []
