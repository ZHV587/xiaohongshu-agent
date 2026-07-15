from data_foundation.knowledge.normalizer import normalize_knowledge_text, normalized_hash
from data_foundation.knowledge.service import extract_deterministic_metadata


def test_normalizer_uses_nfc_removes_invisible_controls_and_preserves_layout_emoji():
    raw = "  Cafe\u0301\u200b\x00\u202e\r\n\r\n👩\u200d💻 CTA\t保留  "

    normalized = normalize_knowledge_text(raw)

    assert normalized == "Café\n\n👩\u200d💻 CTA\t保留"
    assert normalized_hash(normalized) == normalized_hash(
        normalize_knowledge_text("Café\n\n👩\u200d💻 CTA\t保留")
    )


def test_deterministic_metadata_keeps_required_fields_empty_without_evidence():
    metadata = extract_deterministic_metadata({}, "第一段\n\n第二段")

    assert metadata["niche"] is None
    for key in (
        "tags", "hook_types", "cta_types", "style_tags", "success_factors",
    ):
        assert metadata[key] == []
    assert metadata["structure_tags"] == ["短段落"]
    assert metadata["paragraph_count"] == 2


def test_deterministic_metadata_reads_only_explicit_structured_evidence():
    metadata = extract_deterministic_metadata(
        {
            "niche": "职场",
            "tags": ["复盘", "复盘", "成长"],
            "hook": "反常识",
            "cta": "评论互动",
            "structure_tags": ["问题-方法-行动"],
            "style": "克制",
            "success_factors": ["真实案例"],
        },
        "正文",
    )

    assert metadata == {
        "pipeline_version": "knowledge-enrich-v1",
        "niche": "职场",
        "tags": ["复盘", "成长"],
        "hook_types": ["反常识"],
        "cta_types": ["评论互动"],
        "structure_tags": ["问题-方法-行动"],
        "style_tags": ["克制"],
        "success_factors": ["真实案例"],
        "normalized_length": 2,
        "paragraph_count": 1,
    }


def test_deterministic_metadata_infers_falsifiable_copy_surface_features():
    body = "\n".join(
        [
            "我踩过这些坑，整理给你👇",
            "1. 先写真实场景",
            "2. 再给具体动作",
            "你会怎么写？评论区聊聊，记得收藏并关注，下篇继续。",
        ]
    )

    metadata = extract_deterministic_metadata(
        {
            "title": "3 个避坑点：为什么你的文案没人看？",
            "body": body,
            "tags": ["文案"],
        },
        f"3 个避坑点：为什么你的文案没人看？\n\n{body}",
    )

    assert metadata["hook_types"] == ["数字清单", "避坑警示", "问题悬念"]
    assert metadata["cta_types"] == ["评论互动", "收藏", "关注追更"]
    assert metadata["structure_tags"] == ["清单体", "中段落"]
    assert metadata["style_tags"] == ["emoji点缀", "清单表达", "第一人称"]
    assert metadata["paragraph_count"] == 4
    assert metadata["niche"] is None
    assert metadata["success_factors"] == []


def test_explicit_writing_labels_override_surface_inference():
    metadata = extract_deterministic_metadata(
        {
            "title": "3 个避坑问题？",
            "body": "1. 我先做\n2. 我再做\n评论区收藏关注",
            "hook_type": "专家背书",
            "cta_type": "私信咨询",
            "structure": "故事弧",
            "style": "克制叙事",
        },
        "正文",
    )

    assert metadata["hook_types"] == ["专家背书"]
    assert metadata["cta_types"] == ["私信咨询"]
    assert metadata["structure_tags"] == ["故事弧"]
    assert metadata["style_tags"] == ["克制叙事"]


def test_feishu_fields_are_authoritative_metadata_and_niche_can_use_fixed_taxonomy():
    metadata = extract_deterministic_metadata(
        {
            "fields": {
                "垂类": [{"text": "护肤"}],
                "话题标签": ["敏感肌", "防晒"],
                "开头钩子": "痛点前置",
                "互动方式": "评论区答疑",
                "内容结构": "场景-误区-动作",
                "文案风格": "朋友聊天",
                "成功要素": ["前后对比", "真人实测"],
            }
        },
        "敏感肌防晒实测正文",
        title="敏感肌防晒怎么选",
    )

    assert metadata["niche"] == "护肤"
    assert metadata["tags"] == ["敏感肌", "防晒"]
    assert metadata["hook_types"] == ["痛点前置"]
    assert metadata["cta_types"] == ["评论区答疑"]
    assert metadata["structure_tags"] == ["场景-误区-动作"]
    assert metadata["style_tags"] == ["朋友聊天"]
    assert metadata["success_factors"] == ["前后对比", "真人实测"]
