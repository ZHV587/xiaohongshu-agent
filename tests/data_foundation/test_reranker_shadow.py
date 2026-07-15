from types import SimpleNamespace
import uuid

import pytest

from data_foundation.reranker_shadow import execute_shadow_rerank


def _candidate(seed: int):
    return SimpleNamespace(resource_id=str(uuid.UUID(int=seed)), resource_version=1)


def test_shadow_reranker_measures_reorder_without_mutating_candidates() -> None:
    candidates = [_candidate(1), _candidate(2), _candidate(3), _candidate(4)]
    observation = execute_shadow_rerank(
        query="露营",
        ranked_candidates=candidates,
        reranker=lambda **_: [
            (candidates[1].resource_id, 1),
            (candidates[0].resource_id, 1),
            (candidates[3].resource_id, 1),
            (candidates[2].resource_id, 1),
        ],
    )
    assert observation.top1_changed is True
    assert observation.candidate_count == 4
    assert observation.mean_rank_displacement == 1.0
    assert len(observation.baseline_order_hash) == 64
    assert observation.baseline_order_hash != observation.shadow_order_hash
    assert [item.resource_id for item in candidates] == [
        str(uuid.UUID(int=seed)) for seed in range(1, 5)
    ]


def test_shadow_reranker_cannot_inject_or_drop_authorized_identity() -> None:
    candidates = [_candidate(1), _candidate(2)]
    with pytest.raises(ValueError, match="authorized candidate set"):
        execute_shadow_rerank(
            query="露营",
            ranked_candidates=candidates,
            reranker=lambda **_: [
                (candidates[0].resource_id, 1),
                (str(uuid.UUID(int=99)), 1),
            ],
        )
