from __future__ import annotations
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from data_foundation.metric_parse import weighted_engagement

# 绝对相关度下限闸门默认值(仅作用于语义/余弦路径)。
# 经验依据(生产实测,租户 default,Qwen3-Embedding-4B):
#   - 相关查询"护肤"(语料内)加前缀后 top 余弦 ≈ 0.65
#   - 无关查询"露营装备推荐"(语料外)加前缀后 top 余弦 ≈ 0.46
# 默认取 0.50,落在 0.46(应拒) 与 0.65(应纳) 之间。
# ⚠️ 标定口径警示:上述 0.46/0.65 是用标定期临时英文前缀测得,上线默认模板为中文,
# 前缀文本不同会改变余弦分布。0.50 是初值,需在最终中文模板下用多组真实查询重新标定;
# 阈值可经 XHS_EMBEDDING_RELEVANCE_FLOOR 配置覆盖(由 tools 层在查询路径从当前配置解析)。
DEFAULT_RELEVANCE_FLOOR: float = 0.50

# rank_evidence 最终加权配比(四者之和 == 1.0)。
# 去归一化后 relevance 承载真实绝对相关度信号(且闸门已滤掉无关项),故提高其权重。
WEIGHT_RELEVANCE: float = 0.70
WEIGHT_FRESHNESS: float = 0.15
WEIGHT_TYPE: float = 0.10
WEIGHT_PERFORMANCE: float = 0.05

# 效果分对数归一化上界(明文常量)。tanh(.../500) 对对标爆款(万级)恒饱和到 ≈1.0、
# 爆款间无区分;改对数归一化使 10²~10⁶ 量级单调可分。
# log10(1+1e2)/log10(1+1e6)=0.33;1e4→0.67;1e6→1.0,跨 4 个数量级仍单调。
P_SCORE_LOG_CAP: float = 1_000_000.0
_P_SCORE_LOG_DENOM: float = math.log10(1.0 + P_SCORE_LOG_CAP)

_VALID_SCORE_KINDS = {"cosine", "bm25"}


def _parse_aware(value: str) -> datetime:
    """把 source_updated_at 解析为 offset-aware(UTC)datetime。

    外部同步来的时间戳可能不带时区(naive,如本地/裸时间戳)。直接与 offset-aware 的 now 相减会抛
    `TypeError: can't subtract offset-naive and offset-aware datetimes`,被上层 try/except 吞掉后
    时效分静默退化成固定 0.7,使时效加权形同虚设。此处把 naive 一律按 UTC 补齐时区,保证可运算。
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _relevance_score(raw: float, score_kind: str, max_raw_score: float) -> float:
    """relevance 口径分支。

    - cosine:绝对余弦相似度,夹紧到 [0, 1],**不做候选集内归一化**(保留绝对相关度信号)。
    - bm25:无固定上界,候选集内归一化(保留既有行为)。
    """
    if score_kind == "cosine":
        return min(max(raw, 0.0), 1.0)
    return raw / max_raw_score


def rank_evidence(
    tenant_id: str,
    results: list[dict[str, Any]],
    performance_data: dict[str, list[dict[str, Any]]],
    limit: int = 10,
    *,
    score_kind: str,
) -> list[dict[str, Any]]:
    if score_kind not in _VALID_SCORE_KINDS:
        raise ValueError(f"score_kind must be one of {_VALID_SCORE_KINDS}, got {score_kind!r}")
    if not results:
        return []

    max_raw_score = max((float(r.get("score") or 0.0) for r in results), default=1.0)
    if max_raw_score <= 0:
        max_raw_score = 1.0

    candidates = []
    now = datetime.now(timezone.utc)

    for item in results:
        resource_id = item["resource_id"]
        meta = item.get("metadata") or {}

        # 1. Relevance Score(按 score_kind 口径)
        relevance = _relevance_score(float(item.get("score") or 0.0), score_kind, max_raw_score)

        # 2. Freshness Score
        source_updated_str = meta.get("source_updated_at")
        delta_days = 0.0
        if source_updated_str:
            try:
                dt = _parse_aware(source_updated_str)
                delta_days = max(0.0, (now - dt).total_seconds() / 86400.0)
                freshness = math.exp(-0.05 * delta_days)
            except Exception:
                freshness = 0.7
        else:
            freshness = 0.7

        # 3. Type Weight
        rtype = meta.get("type", "doc")
        if rtype in {"performance_metric", "generated_copy"}:
            type_weight = 1.0
        elif rtype == "generated_topic":
            type_weight = 0.8
        else:
            type_weight = 0.6

        # 4. Performance Weight
        p_rows = performance_data.get(resource_id) or []
        p_score = 0.0
        if p_rows:
            best_p = p_rows[0]
            metrics = best_p.get("metrics") or {}
            # 加权互动系数走单一事实源 weighted_engagement(与效果回填 _score 同口径,含单位文本
            # 安全解析)。此处的归一化是对数归一化(去饱和、绝对声量),与回填的÷播放量各自保留。
            engagement = weighted_engagement(metrics)
            if engagement > 0:
                p_score = min(math.log10(1.0 + engagement) / _P_SCORE_LOG_DENOM, 1.0)

        # Final Weighted Score
        final_score = (
            WEIGHT_RELEVANCE * relevance
            + WEIGHT_FRESHNESS * freshness
            + WEIGHT_TYPE * type_weight
            + WEIGHT_PERFORMANCE * p_score
        )

        why = f"根据相关度得分归一化 {relevance:.2f}"
        if source_updated_str:
            why += f"，源端更新于 {delta_days:.1f} 天前 (时效得分 {freshness:.2f})"
        else:
            why += f"，源端更新时间未知 (默认时效得分 {freshness:.2f})"
        if p_score > 0.01:
            why += f"，历史效果良好 (表现分 {p_score:.2f})"

        candidates.append({
            "resource_id": resource_id,
            "title": item["title"],
            "summary": item["summary"],
            "score": round(final_score, 4),
            "why_selected": why,
            "rank_signals": {
                "relevance": round(relevance, 4),
                "freshness": round(freshness, 4),
                "performance": round(p_score, 4)
            },
            "metadata": meta,
        })

    # Sort by Score Descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Prune & Deduplicate
    final_results = []
    for cand in candidates:
        duplicate = False
        # Title Fuzzy Deduplication
        for existing in final_results:
            ratio = SequenceMatcher(None, cand["title"], existing["title"]).ratio()
            if ratio > 0.90:
                duplicate = True
                break
        if not duplicate:
            final_results.append(cand)

    return final_results[:limit]
