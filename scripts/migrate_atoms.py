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
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ATOMS_URL = "https://raw.githubusercontent.com/dontbesilent2025/dbskill/main/%E7%9F%A5%E8%AF%86%E5%BA%93/%E5%8E%9F%E5%AD%90%E5%BA%93/atoms.jsonl"
RESOURCE_TYPE = "dbskill_atom"
FEISHU_TABLE_NAME = "知识原子库"
ACTOR = "migrate_atoms_script"
# 已在飞书知识库「小红书爆单手册」(space_id=7648177996175543260) 内创建。
# Wiki node: GTc6w6aajiEpnDkL5CKc57IJnD4
ATOMS_APP_TOKEN = "U8C4baIMxawaBFsuscNcRQsKnkh"
ATOMS_TABLE_ID = "tblQppgGGbLQwXo9"


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
                    content_json={
                        **{k: atom.get(k) for k in
                           ("id", "knowledge", "original", "url", "date",
                            "topics", "type", "confidence")},
                        "skills": _map_atom_skills(atom.get("skills")),
                    },
                    visibility="team",
                    owner_open_id=None,
                    summary=atom.get("original", "")[:200] or atom["knowledge"][:200],
                    mapping={
                        "system": "dbskill",
                        "external_type": "knowledge_atom",
                        "external_id": atom["id"],
                        "external_url": atom.get("url"),
                        "sync_status": "synced",
                    },
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
    executable = shutil.which("lark-cli") or shutil.which("lark-cli.cmd") or shutil.which("lark-cli.CMD")
    if not executable:
        return {"ok": False, "error": "lark-cli executable not found on PATH"}
    completed = subprocess.run(
        [executable, *shlex.split(cmd), "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    raw = completed.stdout.strip() or completed.stderr.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": raw, "exit_code": completed.returncode}


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


FEISHU_ATOM_FIELDS = [
    "知识内容",
    "原子ID",
    "内容类型",
    "可信度",
    "发布日期",
    "原文摘要",
    "来源链接",
    "主题标签",
    "关联Skill",
]

DBSKILL_TO_LOCAL_SKILL = {
    "dbs-content": "xhs-content",
    "dbs-diagnosis": "xhs-diagnosis",
    "dbs-deconstruct": "xhs-deconstruct",
    "dbs-unblock": "xhs-action",
    "dbs-benchmark": "benchmark-analyst",
}


def _join_cell(value: object) -> str:
    if isinstance(value, list):
        return "，".join(str(item) for item in value if item)
    return str(value or "")


def _map_atom_skills(skills: object) -> list[str]:
    if not isinstance(skills, list):
        return []
    mapped = []
    for skill in skills:
        local_skill = DBSKILL_TO_LOCAL_SKILL.get(str(skill), str(skill))
        if local_skill and local_skill not in mapped:
            mapped.append(local_skill)
    return mapped


def _atom_to_feishu_row(atom: dict) -> list[object]:
    return [
        atom["knowledge"],
        atom["id"],
        atom.get("type", ""),
        atom.get("confidence", ""),
        atom.get("date", ""),
        atom.get("original", ""),
        atom.get("url", ""),
        _join_cell(atom.get("topics")),
        _join_cell(_map_atom_skills(atom.get("skills"))),
    ]


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _write_batch_payload(payload: dict, batch_index: int) -> str:
    temp_dir = Path("large_tool_results") / "dbskill_atoms_import"
    temp_dir.mkdir(parents=True, exist_ok=True)
    payload_path = temp_dir / f"batch_{batch_index:04d}.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return "@" + payload_path.as_posix()


def import_to_feishu(atoms: list[dict], dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] 将写入 {len(atoms)} 条记录到飞书 {FEISHU_TABLE_NAME}")
        return

    ok = skip = 0
    for batch_index, batch in enumerate(_chunks(atoms, 200), start=1):
        payload = {
            "fields": FEISHU_ATOM_FIELDS,
            "rows": [_atom_to_feishu_row(atom) for atom in batch],
        }
        payload_arg = _write_batch_payload(payload, batch_index)
        cmd = shlex.join(["base", "+record-batch-create", "--base-token", ATOMS_APP_TOKEN,
                          "--table-id", ATOMS_TABLE_ID, "--json", payload_arg,
                          "--as", "user"])
        resp = _lark(cmd)
        if resp.get("ok") is True or resp.get("code") == 0:
            ok += len(batch)
        else:
            skip += len(batch)
            print(f"  批次 {batch_index} 跳过 {len(batch)} 条: {resp.get('msg') or resp.get('error')}")

        print(f"  飞书: {min(batch_index * 200, len(atoms))}/{len(atoms)}")
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
