"""飞书多维表格只读工具。

两步:① app_id/secret 换 tenant_access_token;② 拉取整表记录。
返回 {columns, rows},不写死字段映射(设计做法 B:由智能体自行理解表结构)。
"""
import os
from typing import Any

import httpx
from langchain_core.tools import tool

FEISHU_BASE = "https://open.feishu.cn/open-apis"

# 核心列白名单关键词:只保留对"分析爆款规律 + 写文案"有用的列,
# 砍掉图片附件/链接/仿写流程/采集系统等噪声列(它们占数据体积大头却无分析价值)。
# 用关键词子串匹配(而非精确列名),容忍飞书表列名的细微变动/前缀 emoji。
_CORE_COLUMN_KEYWORDS = (
    "标题",
    "正文",
    "视频文案",
    "话题标签",
    "分类标签",
    "点赞",
    "收藏",
    "评论数",
    "转发",
    "播放",
    "赞评比",
    "赞藏比",
    "爆款",
    "博主",
    "发布时间",
    "关联搜索词",
)

# 明确排除的噪声关键词(优先级高于白名单:命中即剔除)。
# 防止"隐藏的视频文案修正""仿写图片提示词"等大块噪声混入。
_EXCLUDE_COLUMN_KEYWORDS = (
    "仿写",
    "图片",
    "附件",
    "链接",
    "域名",
    "采集",
    "封面",
    "海外",
    "修正",
    "隐藏",
)


def _is_core_column(name: str) -> bool:
    """判断列是否属于核心分析列(先排除噪声,再匹配白名单)。"""
    if any(kw in name for kw in _EXCLUDE_COLUMN_KEYWORDS):
        return False
    return any(kw in name for kw in _CORE_COLUMN_KEYWORDS)



def fetch_token(app_id: str, app_secret: str) -> str:
    """用应用凭证换取 tenant_access_token。"""
    resp = httpx.post(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书鉴权失败: code={data.get('code')} msg={data.get('msg')}")
    return data["tenant_access_token"]


def read_bitable_records(
    app_id: str,
    app_secret: str,
    bitable_app_token: str,
    table_id: str,
    page_size: int = 200,
    core_only: bool = True,
) -> dict[str, Any]:
    """读取整张多维表的记录,返回列名清单与数据行。

    Args:
        core_only: True(默认)只返回核心分析列(白名单过滤),大幅缩减体积,
            避免超大结果触发 deepagents 转存文件 / 拖慢模型。False 返回全部列。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    token = fetch_token(app_id, app_secret)
    headers = {"Authorization": f"Bearer {token}"}
    rows: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        params: dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        resp = httpx.get(
            f"{FEISHU_BASE}/bitable/v1/apps/{bitable_app_token}/tables/{table_id}/records",
            headers=headers,
            params=params,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书读表失败: code={data.get('code')} msg={data.get('msg')}")
        block = data.get("data", {})
        for item in block.get("items", []):
            rows.append(item.get("fields", {}))
        if block.get("has_more") and block.get("page_token"):
            page_token = block["page_token"]
            continue
        break

    seen: dict[str, None] = {}
    for row in rows:
        seen.update(dict.fromkeys(row))
    columns = list(seen)

    if core_only:
        # 只保留核心列,既裁列名清单,也裁每行内容,显著缩小返回体积。
        core_cols = [c for c in columns if _is_core_column(c)]
        # 兜底:若白名单一列都没命中(表结构大改),退回全列,避免返回空表。
        if core_cols:
            columns = core_cols
            rows = [{c: r.get(c) for c in core_cols if c in r} for r in rows]

    return {"columns": columns, "rows": rows}


@tool
def read_xhs_data(scope: str = "all") -> dict[str, Any]:
    """读取飞书多维表格里的小红书爆款/对标数据。

    返回整表的列名清单与所有数据行,供你分析爆款规律、提炼选题与文案套路。
    你需要自行理解每一列的含义(如标题、正文、点赞、收藏、话题标签等)。

    Args:
        scope: 读取范围,目前固定读取整张表,传 "all" 即可。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    return read_bitable_records(
        os.environ["FEISHU_APP_ID"],
        os.environ["FEISHU_APP_SECRET"],
        os.environ["FEISHU_BITABLE_APP_TOKEN"],
        os.environ["FEISHU_BITABLE_TABLE_ID"],
    )
