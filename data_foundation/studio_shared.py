"""studio 读写共用的底层辅助 + 鉴权判定(领域基础层)。

处于依赖底部:只依赖 db / repositories / performance_feedback,不依赖 studio_api /
internal_api / tools —— 供 operations(只读聚合)与 studio_api 写路径(_persist_*)共用,
杜绝辅助逻辑复制或跨层耦合。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone

from data_foundation.db import connect
from data_foundation.repositories.resource import ResourceRepository

# 发布管线单向状态机:scheduled→published→measured,仅相邻正向可推进。
_PIPELINE_STAGES: tuple[str, ...] = ("scheduled", "published", "measured")


def is_admin_open_id(open_id: str) -> bool:
    """open_id 是否在 XHS_ADMIN_OPEN_IDS 白名单内。空/未设一律 False。"""
    if not open_id:
        return False
    admins = {
        item.strip()
        for item in os.environ.get("XHS_ADMIN_OPEN_IDS", "").split(",")
        if item.strip()
    }
    return open_id in admins


@contextmanager
def repository():
    """资源仓储上下文(connect→ResourceRepository→close),读写共用。"""
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()


def derive_stage(content: dict) -> str | None:
    """发布管线 stage = content_json 的显式 stage 字段(单一事实源)。

    只认写路径落的显式 stage;不对无显式 stage 的历史/外部指标做启发式推断,返回 None。
    """
    stage = content.get("stage")
    return stage if stage in _PIPELINE_STAGES else None


def existing_metric_content(repo, *, tenant_id: str, actor_open_id: str, metric_id: str | None) -> dict:
    """读既有 performance_metric.content_json(幂等合并用);无则空 dict。"""
    if not metric_id:
        return {}
    resource = repo.get_resource(tenant_id, actor_open_id, metric_id)
    return dict(resource.content_json or {}) if resource is not None else {}


def now_iso() -> str:
    """当前 UTC 时间 ISO 串(发布时间戳缺省值)。"""
    return datetime.now(timezone.utc).isoformat()


def day_of_month(value) -> int | None:
    """'YYYY-MM-DD' → 当月第几天(int);非法 → None。供日历按天分组。"""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return int(value[8:10])
    except ValueError:
        return None
