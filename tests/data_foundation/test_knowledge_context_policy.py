import uuid

import pytest

from data_foundation.knowledge.source_qualification import (
    XHS_COPYWRITING_DOMAIN,
    is_explicitly_qualified,
    qualify_base_record,
    qualify_wiki_document,
)
from data_foundation.retrieval_policy import (
    graph_edge_types,
    infer_retrieval_task,
    select_task_bundle,
    validate_retrieval_task,
)
from data_foundation.writing_context import WritingContext, context_from_payload


def test_feishu_base_requires_explicit_table_domain_and_complete_body() -> None:
    config = {
        "knowledge_enabled": True,
        "knowledge_domain": XHS_COPYWRITING_DOMAIN,
        "knowledge_table_ids": ["tbl-qualified"],
        "minimum_content_chars": 20,
    }
    qualified = qualify_base_record(
        table_id="tbl-qualified",
        title="露营装备清单",
        body="第一次露营只带这三件核心装备，少买也不会踩坑。",
        source_config=config,
    )
    assert is_explicitly_qualified(qualified) is True
    assert qualify_base_record(
        table_id="tbl-other",
        title="露营装备清单",
        body="第一次露营只带这三件核心装备，少买也不会踩坑。",
        source_config=config,
    )["reason"] == "BASE_TABLE_NOT_ALLOWLISTED"
    assert qualify_base_record(
        table_id="tbl-qualified",
        title="短标题",
        body="太短",
        source_config=config,
    )["reason"] == "SOURCE_CONTENT_INCOMPLETE"


def test_feishu_wiki_fails_closed_without_explicit_knowledge_switch() -> None:
    content = "这是一段完整的小红书写作方法正文，包含钩子、结构与互动设计。"
    assert qualify_wiki_document(
        title="写作方法", content=content, source_config={}
    )["eligible"] is False
    assert qualify_wiki_document(
        title="写作方法",
        content=content,
        source_config={
            "knowledge_enabled": True,
            "knowledge_domain": XHS_COPYWRITING_DOMAIN,
        },
    )["eligible"] is True


def test_writing_context_has_stable_isolated_scope_key() -> None:
    account_id = str(uuid.uuid4())
    context = WritingContext(account_id=account_id, niche="  职场 成长 ")
    assert context.scope_key == f"account={account_id};niche=职场 成长"
    assert context_from_payload(context.payload()) == context
    assert WritingContext().scope_key == "global"
    with pytest.raises(ValueError, match="UUID"):
        WritingContext(account_id="not-an-account")


@pytest.mark.parametrize(
    ("query", "task"),
    [
        ("写一篇露营文案", "copywriting"),
        ("照着这篇仿写", "imitation"),
        ("拆解这篇爆款", "teardown"),
        ("帮我出三个选题", "topic"),
        ("把这段润色短一点", "polish"),
        ("诊断账号为什么没效果", "diagnosis"),
    ],
)
def test_retrieval_task_inference_is_deterministic(query: str, task: str) -> None:
    assert infer_retrieval_task(query) == task
    assert validate_retrieval_task(task, query=query) == task
    assert graph_edge_types(task)


def test_task_bundle_respects_kind_targets_and_keeps_original_relative_order() -> None:
    class Item:
        def __init__(self, name: str, asset_kind: str):
            self.name = name
            self.asset_kind = asset_kind

    items = [
        Item("copy-1", "copy"),
        Item("source-1", "source_material"),
        Item("pattern-1", "pattern"),
        Item("teardown-1", "teardown"),
        Item("copy-2", "copy"),
    ]
    selected = select_task_bundle(items, task="copywriting", limit=4)
    assert [item.name for item in selected] == [
        "copy-1",
        "source-1",
        "pattern-1",
        "teardown-1",
    ]
