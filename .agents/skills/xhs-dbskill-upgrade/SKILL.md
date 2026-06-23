---
name: xhs-dbskill-upgrade
description: |
  dbskill 融合升级审计。检查上游 dontbesilent2025/dbskill 版本、技能清单、知识原子和本地 xhs-* 映射是否漂移。
  触发方式：「检查dbskill版本」「同步dbskill」「dbskill升级」「dbskill融合审计」
---

# xhs-dbskill-upgrade：dbskill 升级审计

这是开发者/维护者 skill，不面向普通小红书创作者工作流。

---

## 使用场景

- 用户要求检查 `dontbesilent2025/dbskill` 是否有新版本
- 用户要求确认本地 `xhs-*` 是否覆盖上游 `/dbs-*`
- 用户要求重新同步知识原子库
- 用户要求审计飞书和数据库中的 `dbskill_atom`

---

## 审计清单

1. 浏览上游 GitHub README，确认最新版本号和工具清单
2. 对照 `.agents/skills/` 下的本地 skill
3. 检查 `prompts.py` 是否覆盖 `/dbs-*` alias
4. 检查飞书 `dbskill 知识原子库` 记录数和字段结构
5. 检查 Postgres `resources.type = "dbskill_atom"` 数量
6. 抽样检查 `content_json.skills` 是否使用本地 `xhs-*`
7. 更新 `docs/dbskill-integration-matrix.md` 或实施计划

---

## 输出格式

```
## dbskill 升级审计

**上游版本**：{版本}
**本地状态**：{完整/部分/缺口}

**已覆盖**：
- {能力}

**缺口**：
- {能力和原因}

**数据状态**：
- 飞书：{数量}
- Postgres：{数量}
- dbs 残留：{数量}

**建议动作**：
1. {动作}
2. {动作}
```

