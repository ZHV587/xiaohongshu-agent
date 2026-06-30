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

import calendar as _calendar
import logging
import uuid as _uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.db import connect
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


def _compact_number(value: float | int) -> str:
    """非负数 → 中文紧凑计数串(亿/万)。整数省略小数。"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "0"
    if n < 0:
        n = 0.0
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿".replace(".0亿", "亿")
    if n >= 10_000:
        return f"{n / 10_000:.1f}万".replace(".0万", "万")
    return str(int(n)) if float(n).is_integer() else f"{n:.1f}"


def _as_datetime(value) -> datetime | None:
    """把 datetime / ISO 串解析为 tz-aware datetime;不可解析 → None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _format_dt(value) -> str:
    """datetime / ISO 串 → 'MM-DD HH:MM';无效 → ''。"""
    parsed = _as_datetime(value)
    return parsed.strftime("%m-%d %H:%M") if parsed is not None else ""


def _delta_pct(recent: float, previous: float) -> int:
    """周环比增长百分比(真实窗口派生)。无上周基数时:有本周 → 100,否则 0。"""
    if previous > 0:
        return round((recent - previous) / previous * 100)
    return 100 if recent > 0 else 0


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


def _format_schedule_time(content: dict) -> str:
    """排期项时间显示:'MM-DD HH:MM'(取 scheduled_date/scheduled_time)。"""
    sched_date = content.get("scheduled_date") or ""
    sched_time = content.get("scheduled_time") or ""
    month_day = sched_date[5:10] if isinstance(sched_date, str) and len(sched_date) >= 10 else ""
    return f"{month_day} {sched_time}".strip()


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


# ── 真实数据聚合(数据底座 resources / resource_edges) ──

_DASHBOARD_SPECS = (
    ("likes", "总点赞", "coral", "❤"),
    ("collects", "总收藏", "topic", "⭐"),
    ("comments", "总评论", "success", "💬"),
    ("views", "总曝光", "neutral", "👁"),
)


def _build_dashboard(metric_rows: list[dict]) -> list[dict]:
    """按 performance_metric 真实指标聚合看板卡片;某指标全为 0 则不出卡(不补 0 值占位)。"""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    totals = {key: 0.0 for key, *_ in _DASHBOARD_SPECS}
    recent = {key: 0.0 for key, *_ in _DASHBOARD_SPECS}
    previous = {key: 0.0 for key, *_ in _DASHBOARD_SPECS}
    for row in metric_rows:
        content = dict(row["content_json"] or {})
        metrics = dict(content.get("metrics") or {})
        updated = _as_datetime(row.get("updated_at"))
        for key, *_ in _DASHBOARD_SPECS:
            value = metrics.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            value = float(value)
            totals[key] += value
            if updated is not None and updated >= week_ago:
                recent[key] += value
            elif updated is not None and two_weeks_ago <= updated < week_ago:
                previous[key] += value
    cards: list[dict] = []
    for key, label, tone, icon in _DASHBOARD_SPECS:
        if totals[key] <= 0:
            continue
        cards.append(
            {
                "label": label,
                "value": _compact_number(totals[key]),
                "delta": _delta_pct(recent[key], previous[key]),
                "tone": tone,
                "icon": icon,
            }
        )
    return cards


def _build_library_and_teardown(rows: list[dict]) -> tuple[list[dict], dict]:
    """generated_copy(+measured_by performance_metric)→ 选题库条目 + 爆款拆解标题。

    hot 为已回填条目按真实 score 在本批内归一到 1–100 的相对热度;未回填条目 hot=0
    (真实「暂无效果数据」哨兵)。拆解 points 暂无真实拆解分析数据 → [](需求 11.4)。
    """
    parsed: list[dict] = []
    for row in rows:
        copy_json = dict(row["copy_json"] or {})
        metric_json = dict(row["metric_json"]) if row["metric_json"] is not None else None
        metrics = dict(metric_json.get("metrics") or {}) if metric_json else {}
        score = float(metric_json.get("score", 0.0)) if metric_json else 0.0
        note_url = metric_json.get("note_url") if metric_json else None
        measured = bool(metric_json and metrics)
        if measured:
            status = "已回填"
        elif note_url:
            status = "已发布"
        else:
            status = "草稿"
        likes = metrics.get("likes", 0)
        saves = metrics.get("collects", 0)
        parsed.append(
            {
                "title": row["title"],
                "angle": copy_json.get("source_topic") or row.get("summary") or "",
                "score": score,
                "measured": measured,
                "likes": _compact_number(likes) if likes else "0",
                "saves": _compact_number(saves) if saves else "0",
                "status": status,
            }
        )

    measured_scores = [item["score"] for item in parsed if item["measured"]]
    score_min = min(measured_scores) if measured_scores else 0.0
    score_max = max(measured_scores) if measured_scores else 0.0
    library: list[dict] = []
    for index, item in enumerate(parsed, start=1):
        if item["measured"] and score_max > score_min:
            hot = round(1 + 99 * (item["score"] - score_min) / (score_max - score_min))
        elif item["measured"]:
            hot = 50
        else:
            hot = 0
        library.append(
            {
                "id": index,
                "title": item["title"],
                "angle": item["angle"],
                "hot": hot,
                "likes": item["likes"],
                "saves": item["saves"],
                "status": item["status"],
            }
        )

    teardown = {"title": "", "points": []}
    measured_items = [item for item in parsed if item["measured"]]
    if measured_items:
        top = max(measured_items, key=lambda item: item["score"])
        teardown = {"title": top["title"], "points": []}
    return library, teardown


def _load_analytics(*, tenant_id: str, account: str | None) -> dict:
    """看板 + 选题库 + 拆解。account 指定(单账号)时无真实归属可聚合 → 真实空集合。"""
    if account is not None:
        return {"dashboard": [], "library": [], "teardown": {"title": "", "points": []}}
    conn = connect()
    try:
        metric_rows = conn.execute(
            """
            select content_json, updated_at
            from resources
            where tenant_id = %s and type = 'performance_metric' and status = 'active'
            """,
            (tenant_id,),
        ).fetchall()
        library_rows = conn.execute(
            """
            select c.id::text as id, c.title, c.summary,
                   c.content_json as copy_json, c.updated_at as copy_updated,
                   m.content_json as metric_json
            from resources c
            left join resource_edges e
              on e.tenant_id = c.tenant_id
             and e.source_resource_id = c.id
             and e.edge_type = 'measured_by'
            left join resources m
              on m.tenant_id = c.tenant_id
             and m.id = e.target_resource_id
             and m.type = 'performance_metric'
            where c.tenant_id = %s and c.type = 'generated_copy' and c.status = 'active'
            order by c.updated_at desc, c.id desc
            limit 50
            """,
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()
    dashboard = _build_dashboard([dict(row) for row in metric_rows])
    library, teardown = _build_library_and_teardown([dict(row) for row in library_rows])
    return {"dashboard": dashboard, "library": library, "teardown": teardown}


def _load_schedule_items(*, tenant_id: str, account: str | None) -> list[dict]:
    """日历排期项:performance_metric.content_json 含 scheduled_date 的条目按天分组(需求 12.x)。

    真实来源:写接口(/internal/studio/schedule)把排期落为 generated_copy 的 performance_metric
    (measured_by 边 + content_json.scheduled_date/scheduled_time/account),此处经边回读其归属
    generated_copy 标题。account 指定 → 仅该账号(需求 12.3);无排期 → 真实空集合(需求 12.4)。
    存储不可用直接抛出 → calendar 接口据此返回 503(真实错误,不降级吞错)。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            select c.title as title, m.content_json as metric_json
            from resources m
            join resource_edges e
              on e.tenant_id = m.tenant_id
             and e.target_resource_id = m.id
             and e.edge_type = 'measured_by'
            join resources c
              on c.tenant_id = m.tenant_id
             and c.id = e.source_resource_id
            where m.tenant_id = %s and m.type = 'performance_metric' and m.status = 'active'
              and (m.content_json ->> 'scheduled_date') is not null
            order by m.content_json ->> 'scheduled_date', m.content_json ->> 'scheduled_time'
            """,
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()
    by_day: dict[int, list[dict]] = {}
    for row in rows:
        content = dict(row["metric_json"] or {})
        acct = content.get("account") or ""
        if account is not None and acct != account:
            continue
        day = _day_of_month(content.get("scheduled_date"))
        if day is None:
            continue
        by_day.setdefault(day, []).append(
            {
                "t": row["title"],
                "time": content.get("scheduled_time") or "",
                "tone": "coral",
                "acct": acct,
            }
        )
    return [{"date": day, "items": items} for day, items in sorted(by_day.items())]


def _load_calendar(*, tenant_id: str, account: str | None) -> dict:
    """月份信息(真实当前月)+ 真实排期项(由写接口落库的 scheduled performance_metric 回读)。"""
    now = datetime.now(timezone.utc)
    days = _calendar.monthrange(now.year, now.month)[1]
    first_offset = date(now.year, now.month, 1).weekday()  # 周一=0,对齐 WEEKDAYS=["一".."日"]
    month = {"label": f"{now.year} 年 {now.month} 月", "days": days, "firstOffset": first_offset}
    return {"month": month, "calendar": _load_schedule_items(tenant_id=tenant_id, account=account)}


def _load_accounts(*, tenant_id: str) -> dict:
    """账号矩阵 + 聚合总览。数据底座暂无账号实体模型 → 真实空集合 + overview 全 0(需求 9.5)。"""
    return {
        "accounts": [],
        "overview": {"totalFans": 0, "weekNewFans": 0, "weekPosts": 0, "avgHotRate": 0},
    }


def _load_pipeline(*, tenant_id: str, account: str | None) -> list[dict]:
    """发布管线队列(scheduled/published/measured)。account 指定 → 仅该账号(需求 13.5)。

    真实来源: generated_copy 的 performance_metric(measured_by 边)。stage 经 _derive_stage
    派生(显式 stage 优先,兼容飞书同步历史指标的启发式回退)。契约不变量(P11):
    published/measured 必含非空 link(note_url);不满足者跳过(不 mock 占位链接)。scheduled
    项无 link、时间取 scheduled_date/time。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            select c.id::text as id, c.title,
                   m.content_json as metric_json, m.updated_at as metric_updated
            from resources c
            join resource_edges e
              on e.tenant_id = c.tenant_id
             and e.source_resource_id = c.id
             and e.edge_type = 'measured_by'
            join resources m
              on m.tenant_id = c.tenant_id
             and m.id = e.target_resource_id
             and m.type = 'performance_metric'
            where c.tenant_id = %s and c.type = 'generated_copy' and c.status = 'active'
            order by m.updated_at desc, c.id desc
            limit 50
            """,
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()
    queue: list[dict] = []
    index = 0
    for row in rows:
        content = dict(row["metric_json"] or {})
        acct = content.get("account") or ""
        if account is not None and acct != account:
            continue
        stage = _derive_stage(content)
        if stage is None:
            continue
        note_url = content.get("note_url")
        link = note_url.strip() if isinstance(note_url, str) and note_url.strip() else ""
        if stage in ("published", "measured") and not link:
            # published/measured 必含 link 才满足契约不变量 → 无回链跳过(不 mock 占位链接)。
            continue
        index += 1
        if stage == "scheduled":
            time_text = _format_schedule_time(content)
        else:
            time_text = _format_dt(content.get("published_at") or row.get("metric_updated"))
        item = {
            "id": index,
            "title": row["title"],
            "acct": acct,
            "stage": stage,
            "time": time_text,
        }
        if stage in ("published", "measured"):
            item["link"] = link
        queue.append(item)
    return queue


def _load_recents(*, tenant_id: str, open_id: str) -> list[dict]:
    """登录用户最近创作(generated_topic/generated_copy),按 updated_at 倒序(需求 7.2)。

    status: 存在 measured_by → performance_metric 边视为已沉淀(synced),否则草稿(draft)。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            select r.id::text as id, r.type, r.title, r.updated_at,
                   exists (
                     select 1
                     from resource_edges e
                     join resources m
                       on m.tenant_id = e.tenant_id
                      and m.id = e.target_resource_id
                      and m.type = 'performance_metric'
                     where e.tenant_id = r.tenant_id
                       and e.source_resource_id = r.id
                       and e.edge_type = 'measured_by'
                   ) as measured
            from resources r
            where r.tenant_id = %s and r.owner_open_id = %s
              and r.type in ('generated_topic', 'generated_copy')
              and r.status = 'active'
            order by r.updated_at desc, r.id desc
            limit 20
            """,
            (tenant_id, open_id),
        ).fetchall()
    finally:
        conn.close()
    recents: list[dict] = []
    for index, row in enumerate(rows, start=1):
        recents.append(
            {
                "id": index,
                "icon": "📝" if row["type"] == "generated_copy" else "💡",
                "title": row["title"],
                "status": "synced" if row["measured"] else "draft",
            }
        )
    return recents


def _load_trends(*, tenant_id: str) -> list[dict]:
    """热点趋势。暂无真实外部实时趋势数据源 → 真实空集合(需求 5.3);严禁 mock。"""
    return []


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
        data = _load_analytics(tenant_id=default_tenant_id(), account=account)
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
        data = _load_calendar(tenant_id=default_tenant_id(), account=account)
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
    return _json_ok({"ok": True, **_load_accounts(tenant_id=default_tenant_id())})


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
        queue = _load_pipeline(tenant_id=default_tenant_id(), account=account)
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
        recents = _load_recents(tenant_id=default_tenant_id(), open_id=actor.open_id)
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
    return _json_ok({"ok": True, "trends": _load_trends(tenant_id=default_tenant_id())})


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
