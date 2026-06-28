import scripts.calibrate_relevance_floor as cal


def test_recommend_floor_separated_takes_midpoint():
    # 相关组最低 0.58 > 无关组最高 0.48 → 可分,取中点 0.53
    rec = cal.recommend_floor(
        relevant_scores=[0.65, 0.58, 0.72],
        irrelevant_scores=[0.41, 0.48, 0.30],
    )
    assert rec.separated is True
    assert rec.margin is not None and rec.margin > 0
    assert rec.recommended_floor == round((0.58 + 0.48) / 2, 2)


def test_recommend_floor_overlap_returns_none():
    # 相关组最低 0.45 ≤ 无关组最高 0.50 → 重叠,无单一阈值
    rec = cal.recommend_floor(
        relevant_scores=[0.60, 0.45],
        irrelevant_scores=[0.50, 0.30],
    )
    assert rec.separated is False
    assert rec.recommended_floor is None
    assert "重叠" in rec.note


def test_recommend_floor_empty_group_is_unrecommendable():
    rec = cal.recommend_floor(relevant_scores=[0.6], irrelevant_scores=[])
    assert rec.separated is False
    assert rec.recommended_floor is None
    assert "样本不足" in rec.note


def test_recommend_floor_default_floor_lands_in_band():
    # 复刻 search_ranker 注释里的标定区间:无关 ≤0.48、相关 ≥0.58,默认 0.50 应落在安全带内
    rec = cal.recommend_floor(
        relevant_scores=[0.58, 0.65],
        irrelevant_scores=[0.46, 0.48],
    )
    assert rec.separated is True
    assert rec.irrelevant_max is not None and rec.relevant_min is not None
    # 默认 0.50 落在 (0.48, 0.58] 安全带内
    assert rec.irrelevant_max < 0.50 <= rec.relevant_min
