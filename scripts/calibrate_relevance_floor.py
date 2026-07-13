"""中文相关度下限(XHS_EMBEDDING_RELEVANCE_FLOOR)标定工具。

为什么需要:search_ranker.DEFAULT_RELEVANCE_FLOOR=0.50 是用**标定期临时英文前缀**测得的初值
(见 search_ranker.py 注释:相关查询≈0.65、无关≈0.46)。生产上线默认查询指令模板是**中文**
(config._DEFAULT_QUERY_INSTRUCTION),前缀文本不同会改变余弦分布,0.50 必须在**中文模板 +
真实生产语料**下用多组真实查询重新标定(对齐 user-context:以中文为主场景)。

本工具按**与生产完全一致的查询路径**取分:active index → 历史 embedding profile → 中文指令
前缀 → pgvector 余弦。对每条带标签(相关/无关)的中文查询取其 top 绝对余弦,汇总相关组与
无关组的分布,推荐一个能把两组分开的下限,并判断当前配置的 floor 是否落在安全带内。

⚠️ 只读、不写库、不改配置。产出的推荐值由人工经 admin 配置中心写入 XHS_EMBEDDING_RELEVANCE_FLOOR。

用法(在 langgraph 容器内,带库 + 可用 embedding 网关):
    docker compose exec -T langgraph python scripts/calibrate_relevance_floor.py \
        --actor <能读到生产语料的 open_id> --samples /path/to/samples.json

samples.json 形如(查询用中文真实分布,勿用英文样本):
    {
      "relevant":   ["敏感肌护肤", "新手健身计划", "平价口红测评"],
      "irrelevant": ["量子计算入门", "二手车过户流程", "露营装备推荐"]
    }
不传 --samples 时用内置的少量示例词(仅作冒烟,真实标定务必传入贴合自家语料的查询)。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass


# 内置示例:仅供冒烟,真实标定务必用 --samples 传入贴合自家语料的中文查询。
_DEFAULT_SAMPLES = {
    "relevant": ["敏感肌护肤", "新手健身计划", "平价口红测评", "减脂餐搭配"],
    "irrelevant": ["量子计算入门", "二手车过户流程", "露营装备推荐", "房贷利率计算"],
}


@dataclass(frozen=True)
class FloorRecommendation:
    relevant_min: float | None
    relevant_max: float | None
    irrelevant_min: float | None
    irrelevant_max: float | None
    separated: bool
    margin: float | None
    recommended_floor: float | None
    note: str


def recommend_floor(
    relevant_scores: list[float],
    irrelevant_scores: list[float],
) -> FloorRecommendation:
    """纯函数:由相关/无关两组 top 余弦分数推荐下限。无网络、无 DB,可单测。

    判据:理想阈值应 > 所有无关项的 top 分(挡掉无关)且 ≤ 所有相关项的 top 分(放行相关)。
    - 两组完全分开(min(relevant) > max(irrelevant)):推荐取两者中点,margin 为间隔宽度。
    - 两组重叠:无单一阈值能完美分开,recommended_floor=None,提示需更好的查询指令/模型或更多样本。
    """
    if not relevant_scores or not irrelevant_scores:
        return FloorRecommendation(
            relevant_min=min(relevant_scores) if relevant_scores else None,
            relevant_max=max(relevant_scores) if relevant_scores else None,
            irrelevant_min=min(irrelevant_scores) if irrelevant_scores else None,
            irrelevant_max=max(irrelevant_scores) if irrelevant_scores else None,
            separated=False,
            margin=None,
            recommended_floor=None,
            note="样本不足:相关组与无关组都必须非空才能标定。",
        )

    rel_min, rel_max = min(relevant_scores), max(relevant_scores)
    irr_min, irr_max = min(irrelevant_scores), max(irrelevant_scores)
    margin = rel_min - irr_max
    separated = margin > 0

    if separated:
        recommended = round((rel_min + irr_max) / 2, 2)
        note = (
            f"两组可分:相关组最低 {rel_min:.3f} > 无关组最高 {irr_max:.3f},间隔 {margin:.3f}。"
            f"推荐取中点 {recommended:.2f}。"
        )
    else:
        recommended = None
        note = (
            f"两组重叠:相关组最低 {rel_min:.3f} ≤ 无关组最高 {irr_max:.3f}(间隔 {margin:.3f})。"
            "无单一阈值能完美分开 —— 检查查询指令模板是否为中文、样本是否贴合真实分布,"
            "或考虑更换 embedding 模型;不要硬取一个会误纳/误拒的阈值。"
        )

    return FloorRecommendation(
        relevant_min=rel_min,
        relevant_max=rel_max,
        irrelevant_min=irr_min,
        irrelevant_max=irr_max,
        separated=separated,
        margin=margin,
        recommended_floor=recommended,
        note=note,
    )


def _top_cosine_for_query(repo, *, tenant_id: str, actor_open_id: str, query: str, top_k: int) -> float:
    """按生产查询路径取一条查询的 top 绝对余弦(active index + 中文指令前缀 + pgvector)。

    复用统一检索领域层公开的 embedding helper：标定必须走与线上
    ``retrieve_knowledge`` 完全一致的 active index profile 与查询指令，否则阈值无法迁移到生产。
    """
    from data_foundation.config import resolve_query_instruction
    from data_foundation.search import semantic_search
    from data_foundation.retrieval import embed_query, embedding_query_config_for_index

    active_index = repo.active_embedding_index(tenant_id)
    if active_index is None:
        raise RuntimeError("没有 active embedding index;先让 scheduler 建好索引再标定。")
    query_config = embedding_query_config_for_index(active_index)
    instruction = resolve_query_instruction(query_config.model)
    embedding = embed_query(query, config=query_config, query_instruction=instruction)
    results = semantic_search(
        repo,
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        embedding=embedding,
        embedding_model=active_index.embedding_model,
        top_k=top_k,
    )
    return max((r.score for r in results), default=0.0)


def _collect_scores(repo, *, tenant_id: str, actor_open_id: str, queries: list[str], top_k: int) -> list[tuple[str, float]]:
    scored: list[tuple[str, float]] = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        score = _top_cosine_for_query(repo, tenant_id=tenant_id, actor_open_id=actor_open_id, query=q, top_k=top_k)
        scored.append((q, score))
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(description="中文相关度下限标定(只读)")
    parser.add_argument("--actor", required=True, help="能读到生产语料的 open_id(ACL 与线上查询一致)")
    parser.add_argument("--tenant", default=None, help="租户;省略用 XHS_DEFAULT_TENANT_ID")
    parser.add_argument("--samples", default=None, help="样本 JSON 路径({relevant:[...], irrelevant:[...]})")
    parser.add_argument("--top-k", type=int, default=10, help="每条查询取 top_k 候选的最高分(默认 10)")
    args = parser.parse_args()

    from data_foundation.config import current_relevance_floor
    from data_foundation.db import connect
    from data_foundation.permissions import default_tenant_id
    from data_foundation.repositories.resource import ResourceRepository

    tenant_id = args.tenant or default_tenant_id()
    if args.samples:
        with open(args.samples, "r", encoding="utf-8") as fp:
            samples = json.load(fp)
    else:
        samples = _DEFAULT_SAMPLES
        print("⚠️  未传 --samples,使用内置示例词(仅冒烟)。真实标定请传贴合自家语料的中文查询。\n")

    relevant_queries = list(samples.get("relevant") or [])
    irrelevant_queries = list(samples.get("irrelevant") or [])

    conn = connect()
    try:
        repo = ResourceRepository(conn)
        relevant = _collect_scores(repo, tenant_id=tenant_id, actor_open_id=args.actor, queries=relevant_queries, top_k=args.top_k)
        irrelevant = _collect_scores(repo, tenant_id=tenant_id, actor_open_id=args.actor, queries=irrelevant_queries, top_k=args.top_k)
    finally:
        conn.close()

    print(f"== 相关组(应放行,期望高分)tenant={tenant_id} ==")
    for q, s in sorted(relevant, key=lambda x: x[1]):
        print(f"  {s:.3f}  {q}")
    print("== 无关组(应挡掉,期望低分)==")
    for q, s in sorted(irrelevant, key=lambda x: x[1], reverse=True):
        print(f"  {s:.3f}  {q}")

    rec = recommend_floor([s for _, s in relevant], [s for _, s in irrelevant])
    current = current_relevance_floor()

    print("\n== 标定结论 ==")
    print(rec.note)
    print(f"当前生效 floor(current_relevance_floor): {current:.2f}")
    if rec.recommended_floor is not None:
        print(f"推荐 floor: {rec.recommended_floor:.2f}")
        if rec.irrelevant_max is not None and rec.relevant_min is not None:
            in_band = rec.irrelevant_max < current <= rec.relevant_min
            verdict = "落在安全带内,可沿用" if in_band else "未落在安全带内,建议改为推荐值"
            print(f"当前 floor 判定:{verdict}(安全带 ({rec.irrelevant_max:.3f}, {rec.relevant_min:.3f}])")
        print("\n如需采用:在管理员配置中心把 XHS_EMBEDDING_RELEVANCE_FLOOR 设为推荐值(不要直接改源码默认)。")
    else:
        print("无法给出单一推荐阈值(见上)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
