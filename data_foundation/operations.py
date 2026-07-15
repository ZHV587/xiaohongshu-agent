"""studio 运营数据只读聚合(领域层,唯一真源)。

被 studio_api 的 BFF 读 handler 与 tools.py 的 agent 工具共同消费;不依赖二者(无横向耦合)。
纯读:只查真实数据,数据不足返回真实空集合,不 mock。
"""
from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timedelta, timezone

from data_foundation.db import connect
from data_foundation.repositories.account import AccountRepository
from data_foundation.studio_shared import (
    day_of_month,
    derive_stage,
)
from data_foundation.writing_context import WritingContext


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


def _format_schedule_time(content: dict) -> str:
    """排期项时间显示:'MM-DD HH:MM'(取 scheduled_date/scheduled_time)。"""
    sched_date = content.get("scheduled_date") or ""
    sched_time = content.get("scheduled_time") or ""
    month_day = sched_date[5:10] if isinstance(sched_date, str) and len(sched_date) >= 10 else ""
    return f"{month_day} {sched_time}".strip()


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


def load_owned_account_context(
    *, tenant_id: str, actor_open_id: str, account: str
) -> WritingContext:
    """验证单账号访问权，并返回账号表中的权威写作上下文。"""
    conn = connect()
    try:
        return AccountRepository(conn).get_owned_context(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            account_id=account,
        )
    finally:
        conn.close()


def load_analytics(*, tenant_id: str, account: str | None) -> dict:
    """看板 + 选题库 + 拆解；账号过滤以精确版本 resource_contexts 为准。"""
    conn = connect()
    try:
        metric_rows = conn.execute(
            """
            with latest_metric as (
              select distinct on (rv.resource_id)
                     rv.resource_id, rv.version, rv.content_json, rv.created_at
              from resource_versions rv
              join resources live
                on live.tenant_id = rv.tenant_id and live.id = rv.resource_id
              where rv.tenant_id = %s and live.type = 'performance_metric'
                and live.status = 'active'
              order by rv.resource_id, rv.version desc
            )
            select distinct on (metric.resource_id)
                   metric.content_json, metric.created_at as updated_at
            from latest_metric metric
            join resource_edges edge
              on edge.tenant_id = %s
             and edge.target_resource_id = metric.resource_id
             and edge.target_resource_version = metric.version
             and edge.edge_type = 'measured_by'
            left join resource_contexts context
              on context.tenant_id = edge.tenant_id
             and context.resource_id = edge.source_resource_id
             and context.resource_version = edge.source_resource_version
            where (%s::uuid is null or context.account_id = %s::uuid)
            order by metric.resource_id, edge.created_at desc
            """,
            (tenant_id, tenant_id, account, account),
        ).fetchall()
        library_rows = conn.execute(
            """
            with latest_metric as (
              select distinct on (rv.resource_id)
                     rv.resource_id, rv.version, rv.content_json, rv.created_at
              from resource_versions rv
              join resources live
                on live.tenant_id = rv.tenant_id and live.id = rv.resource_id
              where rv.tenant_id = %s and live.type = 'performance_metric'
                and live.status = 'active'
              order by rv.resource_id, rv.version desc
            )
            select c.id::text as id, c.title, c.summary,
                   exact.content_json as copy_json, exact.created_at as copy_updated,
                   metric.content_json as metric_json
            from resources c
            join lateral (
              select rv.version, rv.content_json, rv.created_at
              from resource_versions rv
              where rv.tenant_id = c.tenant_id and rv.resource_id = c.id
              order by rv.version desc
              limit 1
            ) exact on true
            left join lateral (
              select latest.content_json, edge.source_resource_version
              from resource_edges edge
              join latest_metric latest
                on latest.resource_id = edge.target_resource_id
               and latest.version = edge.target_resource_version
              where edge.tenant_id = c.tenant_id
                and edge.source_resource_id = c.id
                and edge.edge_type = 'measured_by'
              order by latest.created_at desc, edge.id desc
              limit 1
            ) metric on true
            left join resource_contexts context
              on context.tenant_id = c.tenant_id
             and context.resource_id = c.id
             and context.resource_version = coalesce(
                   metric.source_resource_version, exact.version
                 )
            where c.tenant_id = %s and c.type = 'generated_copy'
              and c.status = 'active'
              and (%s::uuid is null or context.account_id = %s::uuid)
            order by c.updated_at desc, c.id desc
            limit 50
            """,
            (tenant_id, tenant_id, account, account),
        ).fetchall()
    finally:
        conn.close()
    dashboard = _build_dashboard([dict(row) for row in metric_rows])
    library, teardown = _build_library_and_teardown([dict(row) for row in library_rows])
    return {"dashboard": dashboard, "library": library, "teardown": teardown}


def _load_schedule_items(*, tenant_id: str, account: str | None) -> list[dict]:
    """日历排期项:performance_metric.content_json 含 scheduled_date 的条目按天分组(需求 12.x)。

    真实来源:写接口(/internal/studio/schedule)把排期落为 generated_copy 的 performance_metric
    (measured_by 边 + content_json.scheduled_date/scheduled_time),此处经边和 resource_contexts
    回读精确版本标题与账号归属。account 指定 → 仅该账号;无排期 → 真实空集合。
    存储不可用直接抛出 → calendar 接口据此返回 503(真实错误,不降级吞错)。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            with latest_metric as (
              select distinct on (rv.resource_id)
                     rv.resource_id, rv.version, rv.content_json
              from resource_versions rv
              join resources live
                on live.tenant_id = rv.tenant_id and live.id = rv.resource_id
              where rv.tenant_id = %s and live.type = 'performance_metric'
                and live.status = 'active'
              order by rv.resource_id, rv.version desc
            )
            select c.id::text as resource_id,
                   coalesce(nullif(cv.content_json->>'title', ''), c.title) as title,
                   metric.content_json as metric_json,
                   context.account_id::text as account_id
            from latest_metric metric
            join resource_edges e
              on e.tenant_id = %s
             and e.target_resource_id = metric.resource_id
             and e.target_resource_version = metric.version
             and e.edge_type = 'measured_by'
            join resources c
              on c.tenant_id = e.tenant_id
             and c.id = e.source_resource_id
            left join resource_versions cv
              on cv.tenant_id = c.tenant_id
             and cv.resource_id = c.id
             and cv.version = e.source_resource_version
            left join resource_contexts context
              on context.tenant_id = e.tenant_id
             and context.resource_id = e.source_resource_id
             and context.resource_version = e.source_resource_version
            where (metric.content_json ->> 'scheduled_date') is not null
              and (%s::uuid is null or context.account_id = %s::uuid)
            order by metric.content_json ->> 'scheduled_date',
                     metric.content_json ->> 'scheduled_time'
            """,
            (tenant_id, tenant_id, account, account),
        ).fetchall()
    finally:
        conn.close()
    by_day: dict[int, list[dict]] = {}
    for row in rows:
        content = dict(row["metric_json"] or {})
        acct = row["account_id"] or ""
        day = day_of_month(content.get("scheduled_date"))
        if day is None:
            continue
        by_day.setdefault(day, []).append(
            {
                "t": row["title"],
                "time": content.get("scheduled_time") or "",
                "tone": "coral",
                "acct": acct,
                "resourceId": row["resource_id"],
                "resourceVersion": content.get("target_resource_version"),
            }
        )
    return [{"date": day, "items": items} for day, items in sorted(by_day.items())]


def load_calendar(*, tenant_id: str, account: str | None) -> dict:
    """月份信息(真实当前月)+ 真实排期项(由写接口落库的 scheduled performance_metric 回读)。"""
    now = datetime.now(timezone.utc)
    days = _calendar.monthrange(now.year, now.month)[1]
    first_offset = date(now.year, now.month, 1).weekday()  # 周一=0,对齐 WEEKDAYS=["一".."日"]
    month = {"label": f"{now.year} 年 {now.month} 月", "days": days, "firstOffset": first_offset}
    return {"month": month, "calendar": _load_schedule_items(tenant_id=tenant_id, account=account)}


def load_accounts(*, tenant_id: str, actor_open_id: str) -> dict:
    """当前用户的账号矩阵 + 真实档案/近七天创作聚合。"""
    conn = connect()
    try:
        rows = conn.execute(
            """
            select account.id::text as id,
                   account.display_name,
                   account.niche,
                   account.is_default,
                   account.metadata,
                   count(distinct case
                     when exact_live.type = 'generated_copy'
                      and exact.created_at >= now() - interval '7 days'
                     then context.resource_id
                   end)::int as week_posts,
                   coalesce(avg(case
                     when metric_exact.created_at >= now() - interval '7 days'
                     then nullif(metric_exact.content_json->'normalized_performance'->>'score', '')::double precision
                   end), 0.0) as hot_rate
            from xhs_accounts account
            left join resource_contexts context
              on context.tenant_id = account.tenant_id
             and context.account_id = account.id
            left join resource_versions exact
              on exact.tenant_id = context.tenant_id
             and exact.resource_id = context.resource_id
             and exact.version = context.resource_version
            left join resources exact_live
              on exact_live.tenant_id = context.tenant_id
             and exact_live.id = context.resource_id
            left join resource_edges measured
              on measured.tenant_id = context.tenant_id
             and measured.source_resource_id = context.resource_id
             and measured.source_resource_version = context.resource_version
             and measured.edge_type = 'measured_by'
             and exact_live.type = 'generated_copy'
            left join resource_versions metric_exact
              on metric_exact.tenant_id = measured.tenant_id
             and metric_exact.resource_id = measured.target_resource_id
             and metric_exact.version = measured.target_resource_version
            where account.tenant_id = %s and account.owner_open_id = %s
              and account.status = 'active'
            group by account.id, account.display_name, account.niche,
                     account.is_default, account.metadata
            order by account.is_default desc, account.updated_at desc, account.id
            """,
            (tenant_id, actor_open_id),
        ).fetchall()
    finally:
        conn.close()
    accounts: list[dict] = []
    tones = ("coral", "topic", "draft")
    for index, row in enumerate(rows):
        metadata = dict(row["metadata"] or {})
        fans = max(int(metadata.get("fans") or 0), 0)
        delta = max(int(metadata.get("week_new_fans") or 0), 0)
        hot = round(float(row["hot_rate"] or 0.0) * 100)
        name = str(row["display_name"])
        accounts.append(
            {
                "id": str(row["id"]),
                "handle": name,
                "niche": str(row["niche"] or "未设置垂类"),
                # 展示占位与机器写作上下文分离，避免“未设置垂类”进入画像 scope。
                "writingNiche": str(row["niche"]) if row["niche"] else None,
                "initial": name[:1],
                "fans": _compact_number(fans),
                "fansNum": fans,
                "dFans": delta,
                "posts": int(row["week_posts"] or 0),
                "hot": hot,
                "status": "主力" if row["is_default"] else "成长",
                "tone": tones[index % len(tones)],
            }
        )
    total_fans = sum(item["fansNum"] for item in accounts)
    week_new = sum(item["dFans"] for item in accounts)
    week_posts = sum(item["posts"] for item in accounts)
    average_hot = (
        sum(item["hot"] for item in accounts) / len(accounts) if accounts else 0
    )
    return {
        "accounts": accounts,
        "overview": {
            "totalFans": total_fans,
            "weekNewFans": week_new,
            "weekPosts": week_posts,
            "avgHotRate": average_hot,
        },
    }


def load_pipeline(*, tenant_id: str, account: str | None) -> list[dict]:
    """发布管线队列(scheduled/published/measured)。account 指定 → 仅该账号(需求 13.5)。

    真实来源: generated_copy 的 performance_metric(measured_by 边)。stage 经 derive_stage
    派生(显式 stage)。契约不变量(P11): published/measured 必含非空 link(note_url);
    不满足者跳过(不 mock 占位链接)。scheduled 项无 link、时间取 scheduled_date/time。
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            with latest_metric as (
              select distinct on (rv.resource_id)
                     rv.resource_id, rv.version, rv.content_json, rv.created_at
              from resource_versions rv
              join resources live
                on live.tenant_id = rv.tenant_id and live.id = rv.resource_id
              where rv.tenant_id = %s and live.type = 'performance_metric'
                and live.status = 'active'
              order by rv.resource_id, rv.version desc
            )
            select c.id::text as id,
                   coalesce(nullif(cv.content_json->>'title', ''), c.title) as title,
                   metric.content_json as metric_json,
                   metric.created_at as metric_updated,
                   context.account_id::text as account_id
            from resources c
            join resource_edges e
              on e.tenant_id = c.tenant_id
             and e.source_resource_id = c.id
             and e.edge_type = 'measured_by'
            join latest_metric metric
              on metric.resource_id = e.target_resource_id
             and metric.version = e.target_resource_version
            left join resource_versions cv
              on cv.tenant_id = c.tenant_id
             and cv.resource_id = c.id
             and cv.version = e.source_resource_version
            left join resource_contexts context
              on context.tenant_id = e.tenant_id
             and context.resource_id = e.source_resource_id
             and context.resource_version = e.source_resource_version
            where c.tenant_id = %s and c.type = 'generated_copy'
              and c.status = 'active'
              and (%s::uuid is null or context.account_id = %s::uuid)
            order by metric.created_at desc, c.id desc
            limit 50
            """,
            (tenant_id, tenant_id, account, account),
        ).fetchall()
    finally:
        conn.close()
    queue: list[dict] = []
    index = 0
    for row in rows:
        content = dict(row["metric_json"] or {})
        acct = row["account_id"] or ""
        stage = derive_stage(content)
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
            "resourceId": str(row["id"]),
            "resourceVersion": content.get("target_resource_version"),
            "title": row["title"],
            "acct": acct,
            "stage": stage,
            "time": time_text,
        }
        if stage in ("published", "measured"):
            item["link"] = link
        queue.append(item)
    return queue


def load_recents(*, tenant_id: str, open_id: str) -> list[dict]:
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


def load_trends(*, tenant_id: str) -> list[dict]:
    """热点趋势。暂无真实外部实时趋势数据源 → 真实空集合(需求 5.3);严禁 mock。"""
    return []
