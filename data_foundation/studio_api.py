"""创作运营工作室数据接入的内部聚合路由（studio-data-integration）。

本模块承载工作室账号运营面板（看板/选题库/拆解/日历/账号矩阵/发布管线/最近创作/
热点趋势）的内部 HTTP 聚合端点，以及排期/回填/推进 stage 三个写端点。

设计要点（照搬 internal_api.py 既有范式，不另起炉灶）:
- 鉴权复用 internal_api.py 的 require_user / require_admin（内部密钥 + 身份头二次校验）。
- 响应统一经 _json_ok / _json_error 带 Cache-Control: no-store，且不回带身份令牌。
- 路由经 internal_api.py 的 internal_routes 注册到内部 HTTP 服务。

internal_api 与本模块互相引用(本模块用其鉴权/响应 helper、它注册本模块的 studio_routes)。
为避免「谁先被 import」导致的循环导入,本模块对 internal_api 的依赖一律延迟到处理函数
调用时再 import(call-time import),使本模块可被任意顺序安全导入。db / permissions 不依赖
本模块,可在顶部正常 import。

铁律: 只渲染真实数据,禁止 mock 业务数据。各 GET 端点的聚合**只来自数据底座真实资源**
(resources / resource_edges):
- analytics(看板/选题库/拆解)←按租户聚合 performance_metric + generated_copy(measured_by 边)。
- recents(最近创作)←登录用户拥有的 generated_topic/generated_copy,按 updated_at 倒序。
- pipeline(发布管线)←generated_copy 的 performance_metric(measured_by 边):scheduled 项来自
  写接口落库的 content_json.scheduled_*;published/measured 必含回链 note_url(契约不变量 P11)。
- calendar.month ←真实当前月份;calendar 排期项 ←写接口(/internal/studio/schedule)落库的
  scheduled performance_metric(按 scheduled_date 分组);无排期时真实空集合。
- accounts ←数据底座暂无「小红书账号矩阵」实体模型 → 真实空集合 + overview 全 0。
- trends ←暂无真实外部实时趋势数据源 → 真实空集合。
数据不足时一律返回真实空集合([]/0),由前端渲染空态,绝不 mock 或补 0 值占位卡片。

账号维度(account)说明: 数据底座当前无「账号归属」字段,故 account 指定时(单账号视图)
无真实归属可聚合 → 按需求返回该账号的真实空集合;未指定 account(矩阵总览,跨账号聚合)
按租户聚合全部可见真实数据,走 require_admin(需求 17.1)。
"""

from __future__ import annotations

import logging
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.db import connect
from data_foundation.operations import (
    load_accounts,
    load_analytics,
    load_calendar,
    load_pipeline,
    load_recents,
    load_trends,
)
from data_foundation.outbox_requests import default_write_requests
from data_foundation.performance_feedback import MEASURED_BY_EDGE, save_performance_metric_resource
from data_foundation.permissions import default_tenant_id
from data_foundation.repositories.resource import ResourceRepository


logger = logging.getLogger(__name__)

# 发布管线单向状态机(需求 13.3/13.4):scheduled→published→measured,仅相邻正向可推进。
_PIPELINE_STAGES = ("scheduled", "published", "measured")
_ALLOWED_TRANSITIONS = frozenset({("scheduled", "published"), ("published", "measured")})


class _StageConflict(Exception):
    """发布管线 stage 推进违反单向状态机(逆向/跨级/无起点),映射 409。"""


@contextmanager
def _repository():
    """写路径资源仓储(与 data_foundation/tools.py 同口径:connect→ResourceRepository→close)。"""
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()


def _account_param(request: Request) -> str | None:
    """读取账号维度过滤参数;空串视为未指定(矩阵总览)。"""
    value = request.query_params.get("account", "").strip()
    return value or None


# ── 格式化 helper(纯函数,中文计数口径,与 UI types.ts 字段对齐) ──


def _now_iso() -> str:
    """当前 UTC 时间 ISO 串(发布时间戳缺省值)。"""
    return datetime.now(timezone.utc).isoformat()


def _day_of_month(value) -> int | None:
    """'YYYY-MM-DD' → 当月第几天(int);非法 → None。供日历按天分组。"""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return int(value[8:10])
    except ValueError:
        return None


def _derive_stage(content: dict) -> str | None:
    """发布管线 stage = performance_metric.content_json 的显式 `stage` 字段(单一事实源)。

    本特性所有写路径(排期/回填/推进 stage)都落显式 `stage`。不做启发式推断、不为
    无显式 stage 的历史/外部指标兜底 —— 这类数据不属于发布管线,返回 None。
    """
    stage = content.get("stage")
    return stage if stage in _PIPELINE_STAGES else None


def _existing_metric_content(repo, *, tenant_id: str, actor_open_id: str, metric_id: str | None) -> dict:
    """读既有 performance_metric.content_json(幂等合并用);无则空 dict。"""
    if not metric_id:
        return {}
    resource = repo.get_resource(tenant_id, actor_open_id, metric_id)
    return dict(resource.content_json or {}) if resource is not None else {}


async def internal_studio_analytics(request: Request) -> JSONResponse:
    """数据看板 + 选题库 + 爆款拆解(按账号聚合 performance_metric)。

    指定账号 → require_user(单账号视图);未指定账号(矩阵总览,跨账号聚合) →
    require_admin(需求 17.1)。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_admin, require_user

    account = _account_param(request)
    actor = require_admin(request) if account is None else require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = load_analytics(tenant_id=default_tenant_id(), account=account)
    except Exception:  # noqa: BLE001 - 不回带异常细节(可能含 DSN/路径),仅记日志
        logger.warning("studio_analytics_aggregation_failed")
        return _json_error(503, "Analytics aggregation unavailable")
    return _json_ok({"ok": True, "account": account, **data})


async def internal_studio_calendar(request: Request) -> JSONResponse:
    """内容日历: 月份信息 + 按日期组织的排期项。

    指定账号 → require_user(单账号视图);未指定账号(矩阵总览,跨账号聚合) →
    require_admin(需求 17.1):底层聚合不带 owner 过滤,无 account 即全租户可见,须 admin。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_admin, require_user

    account = _account_param(request)
    actor = require_admin(request) if account is None else require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        data = load_calendar(tenant_id=default_tenant_id(), account=account)
    except Exception:  # noqa: BLE001
        logger.warning("studio_calendar_aggregation_failed")
        return _json_error(503, "Calendar aggregation unavailable")
    return _json_ok({"ok": True, "account": account, **data})


async def internal_studio_accounts(request: Request) -> JSONResponse:
    """账号矩阵档案 + 聚合总览(跨账号矩阵总览)→ require_admin(需求 17.1)。"""
    from data_foundation.internal_api import _json_ok, require_admin

    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _json_ok({"ok": True, **load_accounts(tenant_id=default_tenant_id())})


async def internal_studio_pipeline(request: Request) -> JSONResponse:
    """发布管线: 待发布/已发布·回链/已回填三阶段队列。

    指定账号 → require_user;未指定账号(矩阵总览)→ require_admin(需求 17.1):
    底层聚合不带 owner 过滤,无 account 即全租户可见,须 admin。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_admin, require_user

    account = _account_param(request)
    actor = require_admin(request) if account is None else require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        queue = load_pipeline(tenant_id=default_tenant_id(), account=account)
    except Exception:  # noqa: BLE001
        logger.warning("studio_pipeline_aggregation_failed")
        return _json_error(503, "Pipeline aggregation unavailable")
    return _json_ok({"ok": True, "account": account, "queue": queue})


async def internal_studio_recents(request: Request) -> JSONResponse:
    """登录用户最近创作列表(按时间倒序)。"""
    from data_foundation.internal_api import _json_error, _json_ok, require_user

    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        recents = load_recents(tenant_id=default_tenant_id(), open_id=actor.open_id)
    except Exception:  # noqa: BLE001
        logger.warning("studio_recents_aggregation_failed")
        return _json_error(503, "Recents aggregation unavailable")
    return _json_ok({"ok": True, "recents": recents})


async def internal_studio_trends(request: Request) -> JSONResponse:
    """热点趋势雷达(真实外部实时信号)。"""
    from data_foundation.internal_api import _json_ok, require_user

    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _json_ok({"ok": True, "trends": load_trends(tenant_id=default_tenant_id())})


def _require_fields(body: dict, fields: tuple[str, ...]) -> str | None:
    """校验请求体含全部必填字段(非空),返回缺失字段名或 None。"""
    for field in fields:
        value = body.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return field
    return None


def _is_uuid(value: object) -> bool:
    """resourceId 在数据底座为 uuid 列;格式非法时提前判 400,避免 Postgres uuid 转换错误冒成 500。"""
    if not isinstance(value, str):
        return False
    try:
        _uuid.UUID(value.strip())
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# ── 写路径:落库 helper(真实数据,复用既有仓储/落库范式;与飞书同步分离失败域) ──


def _best_effort_feishu_draft(actor_open_id: str, *, title: str, content: str, tags: str | None = None) -> None:
    """最佳努力把排期/发布草稿同步飞书 Base(分离失败域)。

    飞书同步与落库为独立失败域:落库已成功提交,飞书失败仅记日志、绝不抛出/阻断(需求 14)。
    未配置飞书或用户未授权时 sync_copy_to_feishu 返回 ok:false(不抛),同样仅记日志。
    """
    try:
        from tools.feishu_actions import sync_copy_to_feishu
        from tools.runtime_identity import identity_config

        result = sync_copy_to_feishu.func(
            title=title or "",
            content=content or "",
            tags=tags,
            config=identity_config(actor_open_id),
        )
        if not result.get("ok"):
            logger.info("studio_feishu_sync_skipped: %s", result.get("error"))
    except Exception as exc:  # noqa: BLE001 - 飞书同步失败不阻断落库
        logger.warning("studio_feishu_sync_failed: %s", type(exc).__name__)


def _best_effort_feishu_metrics(
    actor_open_id: str, *, title: str, metrics: dict, note_url: str | None = None
) -> None:
    """最佳努力把回填效果指标同步飞书采集库(分离失败域,失败仅记日志不阻断落库)。"""
    try:
        from tools.feishu_actions import create_online_note_record
        from tools.runtime_identity import identity_config

        note = {
            "title": title or "",
            "note_url": note_url or "",
            "likes": metrics.get("likes", 0),
            "collects": metrics.get("collects", 0),
            "comments": metrics.get("comments", 0),
            "shares": metrics.get("shares", 0),
        }
        result = create_online_note_record(note, config=identity_config(actor_open_id))
        if not result.get("ok"):
            logger.info("studio_feishu_metrics_skipped: %s", result.get("error"))
    except Exception as exc:  # noqa: BLE001 - 飞书同步失败不阻断落库
        logger.warning("studio_feishu_metrics_failed: %s", type(exc).__name__)


def _persist_schedule(
    *, tenant_id: str, actor_open_id: str, resource_id: str, date: str, time: str, account: str
) -> dict:
    """排期落库:把 generated_copy 落为 stage='scheduled' 的 performance_metric(measured_by 边)。

    幂等:同一 target 复用既有 performance_metric id 原地更新(与 save_performance_metric_resource
    同口径,find_performance_metric_id 定位)。不要求 metrics(排期阶段尚无效果数据)。已进入
    published/measured 的条目不回退 stage(单向状态机),仅刷新排期元数据。落库失败抛出 → 上层
    整体返回失败触发前端回滚。返回 calendar 排期项(date=当月第几天 + item)。
    """
    day = _day_of_month(date)
    if day is None:
        raise ValueError("date must be in 'YYYY-MM-DD' format")
    with _repository() as repo:
        target = repo.get_resource(tenant_id, actor_open_id, resource_id)
        if target is None:
            raise PermissionError("target resource not found or not readable")
        meta = repo.writable_resource_metadata(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
        )
        title = target.title or "未命名笔记"
        with repo.unit_of_work():
            existing_id = repo.find_performance_metric_id(
                tenant_id=tenant_id, target_resource_id=resource_id
            )
            content = _existing_metric_content(
                repo, tenant_id=tenant_id, actor_open_id=actor_open_id, metric_id=existing_id
            )
            content.update(
                {
                    "target_resource_id": resource_id,
                    "scheduled_date": date,
                    "scheduled_time": time,
                    "account": account,
                    "channel": content.get("channel") or "xiaohongshu",
                }
            )
            if _derive_stage(content) not in ("published", "measured"):
                content["stage"] = "scheduled"
            resource = repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=existing_id,
                resource_type="performance_metric",
                title=f"排期 {date} {time} · {title}",
                summary=f"排期 {date} {time} · {account}",
                content_text=f"{title}\n排期 {date} {time}\n账号 {account}",
                content_json=content,
                visibility=meta["visibility"],
                owner_open_id=meta["owner_open_id"],
                outbox_requests=default_write_requests(),
            )
            repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=resource_id,
                target_resource_id=resource.id,
                edge_type=MEASURED_BY_EDGE,
                weight=float(content.get("score") or 0.0),
            )
    # 落库已提交,飞书同步为分离失败域(失败仅记日志不阻断)。
    _best_effort_feishu_draft(actor_open_id, title=title, content=target.content_text or "")
    return {
        "date": day,
        "item": {"t": title, "time": time, "tone": "coral", "acct": account},
    }


def _persist_backfill(
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_id: str,
    metrics: dict,
    published_at: str | None = None,
    note_url: str | None = None,
) -> dict:
    """回填落库:复用 save_performance_metric_resource(幂等 upsert + measured_by 边 + _clean_metrics
    校验 + score)。非数值/负值经 _clean_metrics 抛 ValueError → 上层 400。

    save_performance_metric_resource 会按效果指标契约重建 content_json,故先读既有 note_url/
    published_at/排期元数据,落库后再回写合并(stage=measured + 保留 account/scheduled_*),
    使发布管线/日历 GET 在回填后仍读出归属与回链(端到端自洽)。
    """
    with _repository() as repo:
        existing_id = repo.find_performance_metric_id(
            tenant_id=tenant_id, target_resource_id=resource_id
        )
        prior = _existing_metric_content(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, metric_id=existing_id
        )
        target = repo.get_resource(tenant_id, actor_open_id, resource_id)
        title = target.title if target is not None else resource_id
        # stage/account/scheduled_* 与回链经 extra_content 在同一事务内一次写入(原子):
        # 回填即「已测量」→ stage=measured;保留排期归属与既有回链(note_url),避免回填后
        # 该条在发布管线里因 measured 无 link 被静默剔除(_load_pipeline 对 measured 要求非空 link)。
        carryover = {
            key: prior[key]
            for key in ("account", "scheduled_date", "scheduled_time")
            if prior.get(key)
        }
        carryover["stage"] = "measured"
        result = save_performance_metric_resource(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            target_resource_id=resource_id,
            metrics=metrics,
            published_at=published_at or prior.get("published_at"),
            note_url=note_url or prior.get("note_url"),
            channel=prior.get("channel") or "xiaohongshu",
            extra_content=carryover,
        )
    _best_effort_feishu_metrics(
        actor_open_id, title=title, metrics=metrics, note_url=note_url or prior.get("note_url")
    )
    return {"score": result["score"]}


def _persist_pipeline_stage(
    *, tenant_id: str, actor_open_id: str, resource_id: str, to_stage: str, link: str | None = None
) -> dict:
    """推进发布管线 stage(单向状态机)。scheduled→published(持久化 link)、published→measured。

    逆向/跨级/无起点 → _StageConflict(上层 409)。当前 stage 经 _derive_stage 从既有
    performance_metric 派生。published 需非空 link(上层已校验)。落库失败抛出 → 整体失败。
    """
    with _repository() as repo:
        meta = repo.writable_resource_metadata(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_id=resource_id
        )
        existing_id = repo.find_performance_metric_id(
            tenant_id=tenant_id, target_resource_id=resource_id
        )
        if existing_id is None:
            raise _StageConflict("resource is not in the pipeline; schedule it first")
        content = _existing_metric_content(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, metric_id=existing_id
        )
        current = _derive_stage(content) or "scheduled"
        if (current, to_stage) not in _ALLOWED_TRANSITIONS:
            raise _StageConflict(f"cannot advance from '{current}' to '{to_stage}'")
        target = repo.get_resource(tenant_id, actor_open_id, resource_id)
        title = target.title if target is not None else resource_id
        with repo.unit_of_work():
            content["target_resource_id"] = resource_id
            if to_stage == "published":
                content["note_url"] = link.strip()
                content["published_at"] = content.get("published_at") or _now_iso()
            content["stage"] = to_stage
            resource = repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=existing_id,
                resource_type="performance_metric",
                title=f"{to_stage} · {title}",
                summary=content.get("summary"),
                content_json=content,
                visibility=meta["visibility"],
                owner_open_id=meta["owner_open_id"],
                outbox_requests=default_write_requests(),
            )
            repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=resource_id,
                target_resource_id=resource.id,
                edge_type=MEASURED_BY_EDGE,
                weight=float(content.get("score") or 0.0),
            )
    if to_stage == "published":
        _best_effort_feishu_draft(
            actor_open_id, title=title, content=(target.content_text if target else "") or ""
        )
    return {"stage": to_stage}


async def internal_studio_schedule(request: Request) -> JSONResponse:
    """排期落库 + 飞书同步(写接口,需求 14.1/17.1)。

    校验 resourceId/date/time/account(缺失 400);后端持久化排期(stage='scheduled' 的
    performance_metric + measured_by 边)并经飞书最佳努力同步。落库失败整体返回失败(前端回滚);
    飞书同步失败仅记日志不阻断(分离失败域)。成功返回 calendar scheduled 项。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_user

    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _json_error(400, "Bad Request: invalid JSON body")
    if not isinstance(body, dict):
        return _json_error(400, "Bad Request: body must be an object")
    missing = _require_fields(body, ("resourceId", "date", "time", "account"))
    if missing is not None:
        return _json_error(400, f"Bad Request: missing field '{missing}'")
    if not _is_uuid(body.get("resourceId")):
        return _json_error(400, "Bad Request: 'resourceId' must be a valid uuid")
    try:
        scheduled = _persist_schedule(
            tenant_id=default_tenant_id(),
            actor_open_id=actor.open_id,
            resource_id=str(body["resourceId"]).strip(),
            date=str(body["date"]).strip(),
            time=str(body["time"]).strip(),
            account=str(body["account"]).strip(),
        )
    except ValueError as exc:
        return _json_error(400, f"Bad Request: {exc}")
    except PermissionError:
        return _json_error(403, "Forbidden: resource is not writable")
    except Exception:  # noqa: BLE001 - 落库失败不回带异常细节(可能含 DSN/路径),仅记日志
        logger.warning("studio_schedule_persist_failed")
        return _json_error(500, "Schedule persistence failed")
    return _json_ok({"ok": True, "scheduled": scheduled})


async def internal_studio_backfill(request: Request) -> JSONResponse:
    """数据回填落库为 performance_metric + 飞书同步(写接口,需求 15.1/15.3/15.4/17.1)。

    复用 performance_feedback.save_performance_metric_resource(幂等 upsert + measured_by 边 +
    _clean_metrics 校验)。非数值/负值经 _clean_metrics 抛 ValueError → 捕获返回 400。落库失败
    整体返回失败;飞书同步失败仅记日志不阻断(分离失败域)。成功返回 score。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_user

    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _json_error(400, "Bad Request: invalid JSON body")
    if not isinstance(body, dict):
        return _json_error(400, "Bad Request: body must be an object")
    missing = _require_fields(body, ("resourceId",))
    if missing is not None:
        return _json_error(400, f"Bad Request: missing field '{missing}'")
    if not _is_uuid(body.get("resourceId")):
        return _json_error(400, "Bad Request: 'resourceId' must be a valid uuid")
    if not isinstance(body.get("metrics"), dict):
        return _json_error(400, "Bad Request: missing field 'metrics'")
    try:
        result = _persist_backfill(
            tenant_id=default_tenant_id(),
            actor_open_id=actor.open_id,
            resource_id=str(body["resourceId"]).strip(),
            metrics=body["metrics"],
            published_at=body.get("publishedAt"),
            note_url=body.get("link") or body.get("noteUrl"),
        )
    except ValueError as exc:
        # _clean_metrics 对非数值/负值/空指标抛 ValueError(需求 15.3)。
        return _json_error(400, f"Bad Request: {exc}")
    except PermissionError:
        return _json_error(403, "Forbidden: resource is not writable")
    except Exception:  # noqa: BLE001
        logger.warning("studio_backfill_persist_failed")
        return _json_error(500, "Backfill persistence failed")
    return _json_ok({"ok": True, "score": result["score"]})


async def internal_studio_pipeline_advance(request: Request) -> JSONResponse:
    """推进发布管线 stage(单向状态机,写接口,需求 13.3/13.4/17.1)。

    校验 resourceId/toStage(缺失 400);toStage 仅 published/measured,published 需非空 link。
    单向状态机 scheduled→published(持久化 link)、published→measured;逆向/跨级/无起点 → 409。
    """
    from data_foundation.internal_api import _json_error, _json_ok, require_user

    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _json_error(400, "Bad Request: invalid JSON body")
    if not isinstance(body, dict):
        return _json_error(400, "Bad Request: body must be an object")
    missing = _require_fields(body, ("resourceId", "toStage"))
    if missing is not None:
        return _json_error(400, f"Bad Request: missing field '{missing}'")
    if not _is_uuid(body.get("resourceId")):
        return _json_error(400, "Bad Request: 'resourceId' must be a valid uuid")
    to_stage = str(body["toStage"]).strip()
    if to_stage not in ("published", "measured"):
        return _json_error(400, "Bad Request: toStage must be 'published' or 'measured'")
    link = body.get("link")
    if to_stage == "published" and not (isinstance(link, str) and link.strip()):
        return _json_error(400, "Bad Request: missing field 'link'")
    try:
        result = _persist_pipeline_stage(
            tenant_id=default_tenant_id(),
            actor_open_id=actor.open_id,
            resource_id=str(body["resourceId"]).strip(),
            to_stage=to_stage,
            link=link if isinstance(link, str) else None,
        )
    except _StageConflict as exc:
        return _json_error(409, f"Conflict: {exc}")
    except ValueError as exc:
        return _json_error(400, f"Bad Request: {exc}")
    except PermissionError:
        return _json_error(403, "Forbidden: resource is not writable")
    except Exception:  # noqa: BLE001
        logger.warning("studio_pipeline_advance_failed")
        return _json_error(500, "Pipeline advance failed")
    return _json_ok({"ok": True, "stage": result["stage"]})


# studio 内部路由:由 internal_api.py 的 internal_routes 汇总注册到内部 HTTP 服务。
studio_routes = [
    Route("/internal/studio/analytics", internal_studio_analytics, methods=["GET"]),
    Route("/internal/studio/calendar", internal_studio_calendar, methods=["GET"]),
    Route("/internal/studio/accounts", internal_studio_accounts, methods=["GET"]),
    Route("/internal/studio/pipeline", internal_studio_pipeline, methods=["GET"]),
    Route("/internal/studio/recents", internal_studio_recents, methods=["GET"]),
    Route("/internal/studio/trends", internal_studio_trends, methods=["GET"]),
    Route("/internal/studio/schedule", internal_studio_schedule, methods=["POST"]),
    Route("/internal/studio/backfill", internal_studio_backfill, methods=["POST"]),
    Route(
        "/internal/studio/pipeline-advance",
        internal_studio_pipeline_advance,
        methods=["POST"],
    ),
]


__all__ = ["studio_routes"]
