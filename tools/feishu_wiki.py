"""飞书知识库/Wiki 只读工具（读取知识空间下的文档内容）。

统一走 lark_cli（lark-cli wiki +node-list 和 lark-cli docs +fetch），与写操作保持一致的认证路径。
"""
import os
import json
import shlex
import logging
from typing import Any

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

@tool
def read_feishu_wiki(config: RunnableConfig = None) -> dict[str, Any]:
    """读取飞书知识空间里的文档内容。

    返回所有文档的标题和正文 markdown 格式，供你作为创作文案、选题的参考背景知识。

    Returns:
        {"documents": [{"title": "文档标题", "content": "文档 markdown 内容"}, ...]}
    """
    from tools.lark_cli import lark_cli  # 延迟 import，避免循环依赖

    space_id = os.environ.get("FEISHU_WIKI_SPACE_ID", "")
    if not space_id:
        return {
            "error": "环境变量缺失：FEISHU_WIKI_SPACE_ID 未配置。",
            "documents": [],
        }

    # 1. 列出知识空间的所有节点
    # 使用 --page-all 自动翻页
    args = [
        "wiki", "+node-list",
        "--space-id", space_id,
        "--page-all",
    ]
    command = shlex.join(args)
    resp = lark_cli.func(command, config=config)

    # lark_cli 出错时返回以 "Error" 或 "⚠️" 或 "Feishu" 开头的字符串
    if resp.startswith("Error") or resp.startswith("⚠️") or resp.startswith("Feishu"):
        return {
            "error": f"lark-cli 获取知识库节点失败：{resp}",
            "documents": [],
        }

    try:
        data = json.loads(resp)
    except json.JSONDecodeError:
        return {
            "error": f"lark-cli 返回非 JSON 格式：{resp[:300]}",
            "documents": [],
        }

    # 根据 data["data"]["items"] 遍历
    block = data.get("data", {})
    items = block.get("items", [])
    if not items:
        # 有些 response 结构可能直接在 root，或者为空
        items = data.get("items", [])

    if not items:
        return {"documents": []}

    documents = []
    # 限制拉取文档的总数，避免超时和大量 token 消耗，这里上限设为 20 篇文档
    doc_count = 0
    max_docs = 20

    for item in items:
        obj_type = item.get("obj_type")
        obj_token = item.get("obj_token")
        title = item.get("title", "未命名文档")

        if obj_type in ("docx", "doc") and obj_token:
            if doc_count >= max_docs:
                break
            
            # 2. 读取每个文档的 markdown 内容
            fetch_args = [
                "docs", "+fetch",
                "--doc", obj_token,
                "--doc-format", "markdown",
            ]
            fetch_command = shlex.join(fetch_args)
            fetch_resp = lark_cli.func(fetch_command, config=config)

            if fetch_resp.startswith("Error") or fetch_resp.startswith("⚠️") or fetch_resp.startswith("Feishu"):
                logger.warning(f"Failed to fetch document content for {title} ({obj_token}): {fetch_resp}")
                continue

            try:
                fetch_data = json.loads(fetch_resp)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse document JSON for {title}: {fetch_resp[:300]}")
                continue

            # 从 fetch_data 里提取 content
            content = ""
            if "data" in fetch_data:
                data_block = fetch_data["data"]
                if isinstance(data_block, dict):
                    if "document" in data_block and isinstance(data_block["document"], dict):
                        content = data_block["document"].get("content", "")
                    else:
                        content = data_block.get("content", "")
            
            # 如果没拿到，也可以在 root 找找
            if not content and isinstance(fetch_data, dict):
                content = fetch_data.get("content", "")

            documents.append({
                "title": title,
                "content": content,
            })
            doc_count += 1

    return {"documents": documents}
