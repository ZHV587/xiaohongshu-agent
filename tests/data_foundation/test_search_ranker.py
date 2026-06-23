from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from data_foundation.search_ranker import rank_evidence

def test_rank_evidence_sorting_and_deduplication():
    raw_results = [
        {
            "resource_id": "res-1",
            "title": "露营装备挑选指南",
            "summary": "户外装备",
            "score": 0.9,
            "metadata": {
                "type": "doc",
                "visibility": "private",
                "source_updated_at": datetime.now(timezone.utc).isoformat(),
                "indexed_at": datetime.now(timezone.utc).isoformat()
            }
        },
        {
            "resource_id": "res-2",
            "title": "露营装备挑选指南",  # Fuzzy title duplicate, should be skipped
            "summary": "户外装备2",
            "score": 0.8,
            "metadata": {
                "type": "doc",
                "visibility": "private",
                "source_updated_at": datetime.now(timezone.utc).isoformat(),
                "indexed_at": datetime.now(timezone.utc).isoformat()
            }
        },
        {
            "resource_id": "res-3",
            "title": "如何搭建一个坚固的帐篷",
            "summary": "露营攻略",
            "score": 0.5,
            "metadata": {
                "type": "doc",
                "visibility": "private",
                "source_updated_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                "indexed_at": datetime.now(timezone.utc).isoformat()
            }
        }
    ]
    
    res = rank_evidence("default", raw_results, performance_data={}, limit=10)
    
    assert len(res) == 2  # res-2 should be deduplicated
    assert res[0]["resource_id"] == "res-1"
    assert res[1]["resource_id"] == "res-3"
    
    # relevance score of res-1 is 1.0 (0.9 / 0.9)
    assert res[0]["rank_signals"]["relevance"] == 1.0
    # freshness score of res-3 is e^(-0.05 * 10) = e^(-0.5) ≈ 0.6065
    assert abs(res[1]["rank_signals"]["freshness"] - 0.6065) < 0.001


def test_rank_evidence_incorporates_performance_tanh_score():
    raw_results = [
        {
            "resource_id": "res-1",
            "title": "爆款文案1",
            "summary": "户外装备",
            "score": 0.5,
            "metadata": {
                "type": "generated_copy",
                "visibility": "private",
                "source_updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    ]
    
    performance_data = {
        "res-1": [
            {
                "metrics": {
                    "likes": 200,      # 200
                    "collects": 100,   # 100 * 2 = 200
                    "comments": 20     # 20 * 5 = 100
                }                      # Total equivalent likes = 500 -> tanh(500/500) = tanh(1) ≈ 0.76159
            }
        ]
    }
    
    res = rank_evidence("default", raw_results, performance_data=performance_data, limit=10)
    assert len(res) == 1
    assert abs(res[0]["rank_signals"]["performance"] - 0.7616) < 0.001
