from __future__ import annotations
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

def rank_evidence(
    tenant_id: str,
    results: list[dict[str, Any]],
    performance_data: dict[str, list[dict[str, Any]]],
    limit: int = 10,
) -> list[dict[str, Any]]:
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

        # 1. Relevance Score (Normalized)
        relevance = float(item.get("score") or 0.0) / max_raw_score

        # 2. Freshness Score
        source_updated_str = meta.get("source_updated_at")
        delta_days = 0.0
        if source_updated_str:
            try:
                dt = datetime.fromisoformat(source_updated_str)
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
            likes = float(metrics.get("likes", 0))
            collects = float(metrics.get("collects", 0))
            comments = float(metrics.get("comments", 0))
            p_score = math.tanh((likes + 2 * collects + 5 * comments) / 500.0)

        # Final Weighted Score
        final_score = 0.6 * relevance + 0.2 * freshness + 0.1 * type_weight + 0.1 * p_score

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
