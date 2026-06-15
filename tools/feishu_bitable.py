"""飞书多维表格只读工具。

两步:① app_id/secret 换 tenant_access_token;② 拉取整表记录。
返回 {columns, rows},不写死字段映射(设计做法 B:由智能体自行理解表结构)。
"""
import os
from typing import Any

import httpx
from langchain_core.tools import tool

FEISHU_BASE = "https://open.feishu.cn/open-apis"


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
) -> dict[str, Any]:
    """读取整张多维表的记录,返回列名清单与数据行。

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
    return {"columns": list(seen), "rows": rows}


@tool
def read_xhs_data() -> dict[str, Any]:
    """读取飞书多维表格里的小红书爆款/对标数据。

    返回整表的列名清单与所有数据行,供你分析爆款规律、提炼选题与文案套路。
    你需要自行理解每一列的含义(如标题、正文、点赞、收藏、话题标签等)。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    return read_bitable_records(
        os.environ["FEISHU_APP_ID"],
        os.environ["FEISHU_APP_SECRET"],
        os.environ["FEISHU_BITABLE_APP_TOKEN"],
        os.environ["FEISHU_BITABLE_TABLE_ID"],
    )
