#!/usr/bin/env python3
"""
迁移 dbskill 知识原子到 Postgres 数据底座 + 飞书多维表格。

运行方式（服务器容器内）：
  docker compose exec langgraph python3 /deps/xiaohongshu-agent/scripts/migrate_atoms.py

可选参数：
  --db-only       只导入数据库，跳过飞书
  --feishu-only   只导入飞书，跳过数据库
  --dry-run       只打印统计，不写入任何数据
"""

import json
import os
import shlex
import sys
import time
import urllib.request
from pathlib import Path

ATOMS_URL = "https://raw.githubusercontent.com/dontbesilent2025/dbskill/main/%E7%9F%A5%E8%AF%86%E5%BA%93/%E5%8E%9F%E5%AD%90%E5%BA%93/atoms.jsonl"
RESOURCE_TYPE = "dbskill_atom"
FEISHU_TABLE_NAME = "知识原子库"
ACTOR = "migrate_atoms_script"


# ─── 加载原子 ───────────────────────────────────────────────────────────────────

def load_atoms() -> list[dict]:
    local = Path(__file__).parent.parent / "dbskill_temp" / "知识库" / "原子库" / "atoms.jsonl"
    if local.exists():
        print(f"从本地加载: {local}")
        lines = local.read_text(encoding="utf-8").strip().split("\n")
    else:
        print("从 GitHub 下载 atoms.jsonl ...")
        resp = urllib.request.urlopen(ATOMS_URL, timeout=30)
        lines = resp.read().decode("utf-8").strip().split("\n")

    atoms = [json.loads(line) for line in lines if line.strip()]
    print(f"  共 {len(atoms)} 条知识原子")
    return atoms


# ─── 数据库导入 ─────────────────────────────────────────────────────────────────

def import_to_db(atoms: list[dict], dry_run: bool = False) -> None:
    from data_foundation.tools import _repository
    from data_foundation.permissions import default_tenant_id
    from data_foundation.outbox_requests import default_write_requests

    tenant = default_tenant_id()
    ok = skip = 0

    if dry_run:
        print(f"[dry-run] 将写入 {len(atoms)} 条记录到 tenant={tenant}")
        return

    with _repository() as repo:
        for i, atom in enumerate(atoms):
            try:
                repo.upsert_resource(
                    tenant_id=tenant,
                    actor_open_id=ACTOR,
                    resource_type=RESOURCE_TYPE,
                    title=atom["knowledge"][:100],
                    content_text=(
                        atom["knowledge"]
                        + ("\n\n原文：" + atom["original"] if atom.get("original") else "")
                    ),
                    content_json={k: atom.get(k) for k in
                                  ("id", "knowledge", "original", "url", "date",
                                   "topics", "skills", "type", "confidence")},
                    visibility="team",
                    owner_open_id=None,
                    summary=atom.get("original", "")[:200] or atom["knowledge"][:200],
                    mapping={"dbskill_id": atom["id"]},
                    outbox_requests=default_write_requests(),
                )
                ok += 1
            except Exception as e:
                skip += 1
                if skip <= 5:
                    print(f"  跳过 {atom['id']}: {e}")

            if (i + 1) % 500 == 0:
                print(f"  DB: {i + 1}/{len(atoms)}")

    print(f"DB 完成：{ok} 成功，{skip} 跳过")


# ─── 飞书导入 ───────────────────────────────────────────────────────────────────

def _lark(cmd: str) -> dict:
    from tools.lark_cli import lark_cli
    raw = lark_cli.func(cmd)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": raw}


def _get_or_create_table(app_token: str) -> str | None:
    from tools.feishu_bitable import list_base_tables
    tables, err = list_base_tables(app_token)
    if err:
        print(f"  列表失败: {err}")
        return None
    for t in tables:
        if t["name"] == FEISHU_TABLE_NAME:
            print(f"  已有表: {t['table_id']}")
            return t["table_id"]

    # 创建新表（第一个字段是索引字段，必须是文本）
    payload = json.dumps({
        "table": {
            "name": FEISHU_TABLE_NAME,
            "fields": [{"field_name": "知识内容", "type": 1}],  # 文本（索引字段）
        }
    }, ensure_ascii=False)
    cmd = shlex.join(["base", "+table-create", "--base-token", app_token, "--json", payload])
    resp = _lark(cmd)
    table_id = resp.get("data", {}).get("table_id")
    if not table_id:
        print(f"  建表失败: {resp}")
        return None
    print(f"  已建表: {table_id}")

    # 补充额外字段
    extra_fields = [
        ("原文摘要", 1),      # 文本
        ("来源链接", 15),     # 超链接
        ("原子ID", 1),
        ("主题标签", 4),      # 多选
        ("关联Skill", 4),
        ("内容类型", 3),      # 单选
        ("可信度", 3),
        ("发布日期", 1),
    ]
    for field_name, field_type in extra_fields:
        fp = json.dumps({"field_name": field_name, "type": field_type}, ensure_ascii=False)
        cmd = shlex.join(["base", "+field-create", "--base-token", app_token,
                          "--table-id", table_id, "--json", fp])
        _lark(cmd)

    return table_id


def import_to_feishu(atoms: list[dict], dry_run: bool = False) -> None:
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    if not app_token:
        print("⚠️  FEISHU_BITABLE_APP_TOKEN 未设置，跳过飞书导入")
        return

    if dry_run:
        print(f"[dry-run] 将写入 {len(atoms)} 条记录到飞书 {FEISHU_TABLE_NAME}")
        return

    table_id = _get_or_create_table(app_token)
    if not table_id:
        return

    ok = skip = 0
    for i, atom in enumerate(atoms):
        fields: dict = {
            "知识内容": atom["knowledge"],
            "原子ID": atom["id"],
            "内容类型": atom.get("type", ""),
            "可信度": atom.get("confidence", ""),
            "发布日期": atom.get("date", ""),
        }
        if atom.get("original"):
            fields["原文摘要"] = atom["original"]
        if atom.get("url"):
            fields["来源链接"] = {"text": atom["url"], "link": atom["url"]}
        if atom.get("topics"):
            fields["主题标签"] = atom["topics"]
        if atom.get("skills"):
            fields["关联Skill"] = atom["skills"]

        payload = json.dumps({"fields": fields}, ensure_ascii=False)
        cmd = shlex.join(["base", "+record-create", "--base-token", app_token,
                          "--table-id", table_id, "--json", payload])
        resp = _lark(cmd)
        if resp.get("code") in (None, 0):
            ok += 1
        else:
            skip += 1
            if skip <= 5:
                print(f"  跳过 {atom['id']}: {resp.get('msg')}")

        if (i + 1) % 200 == 0:
            print(f"  飞书: {i + 1}/{len(atoms)}")
            time.sleep(0.3)  # 限流保护

    print(f"飞书完成：{ok} 成功，{skip} 跳过")


# ─── 入口 ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    db_only = "--db-only" in args
    feishu_only = "--feishu-only" in args

    atoms = load_atoms()

    if not feishu_only:
        print(f"\n{'[dry-run] ' if dry_run else ''}--- 步骤1：导入 Postgres ---")
        import_to_db(atoms, dry_run=dry_run)

    if not db_only:
        print(f"\n{'[dry-run] ' if dry_run else ''}--- 步骤2：导入飞书 ---")
        import_to_feishu(atoms, dry_run=dry_run)

    print("\n✅ 完成")
