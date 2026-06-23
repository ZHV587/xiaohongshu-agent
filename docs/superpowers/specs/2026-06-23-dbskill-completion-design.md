# dbskill 补全：xhs-diagnosis / xhs-content-system / xhs-decision v2.0

**日期**：2026-06-23  
**范围**：3个新/更新 Skill 的设计，基于 dontbesilent2025/dbskill 的功能映射

---

## 背景

当前 `.agents/skills/` 有18个 xhs-* skill，但仍有3处缺口：

| 缺口 | 原因 |
|---|---|
| `xhs-diagnosis` 不存在 | 商业问题消解漏斗未迁移 |
| `xhs-content-system` 不存在 | 内容工程化逻辑未迁移 |
| `xhs-decision` 为基础版 | 缺概念炼出/5种工作模式/来源标签 |

---

## 设计一：xhs-diagnosis（新 skill）

### 触发
`/xhs-diagnosis`、`我有个商业问题`、`帮我诊断`、`问诊`、`体检`

### 结构
**Phase 0**：选择模式——问诊（有具体问题）或体检（想拆解商业模式）

**问诊模式**（5层消解漏斗，每层暂停等回应）：
1. 语言陷阱检测（25%）— 关键词能被定义吗？
2. 假设错误检测（25%）— 问题前提成立吗？
3. 逻辑错误检测（20%）— 相关性被当成因果？
4. 事实前提核查（1.5%）— 陈述事实正确吗？
5. 信息充分性判断（2.5%）— 现在能回答吗？
→ 通过漏斗的1%：逻辑推导型/价值选择型/资源约束型/超出边界

**体检模式**（7项检验，每项完成后暂停）：
1. 印钞机检验（input/output/可替代性）
2. 道德检验（模式逼你做好人还是坏人）
3. 定价检验（引流款/利润款价差≥5倍）
4. 需求检验（显性需求 vs 隐性需求）
5. 流量-变现关系检验（平台选择结构）
6. 规模化检验（SOP能否稳定）
7. 成长层级判断（1-7层，不能跳层）
→ 输出诊断报告，调用 `save_session_snapshot` + `sync_diagnosis_to_feishu`（触发审批）

### 集成
- 工具：`save_session_snapshot`、`sync_diagnosis_to_feishu`（二者都已在主 agent tools 列表中）
- `sync_diagnosis_to_feishu` 在 `interrupt_on` → 写入飞书前弹审批确认
- xhs-positioning 增加路由条目 → xhs-diagnosis

---

## 设计二：xhs-content-system（云原生版）

### 触发
`/xhs-content-system`、`内容结构化`、`把内容做成系统`、`内容工程化`

### 与 dbs-content-system 的差异
原版：本地文件系统 + Node.js 脚本  
本版：Postgres 数据底座 + 飞书多维表格，完全云原生

### 结构

**Phase 1：数据底座审计**
- 调用 `get_data_foundation_status` 检查资源量
- 如果资源为0：「数据底座为空，先调用 `sync_feishu_resources` 同步飞书资源再来」
- 如果有数据：展示规模（资源数/类型分布），询问用户聚焦的内容方向

**Phase 2：主题地图生成**
- `search_resources` + `semantic_search_resources` 多角度扫底座
- `graph_expand` 发现主题聚类
- 提炼3-7个核心主题，每个主题含资源数量和代表性 resource_id
- 调用 `write_file` 写入 `/analysis/content-map-{date}.md`（分析文档，不是选题卡片）

**Phase 3：内容单元结构化**
- 对每个主题召回top资源，`get_resource` 精读
- 按5种单元类型分类：观点/案例/方法/概念/问题
- 输出结构化清单（resource_id + 单元类型 + 一句话摘要）

**Phase 4：选题装配**
- 从内容单元组合生成3-5个可立即创作的选题卡片
- 调用 `save_generated_topic(direction, topics, evidence)` 持久化选题卡片到数据库
- 调用 `sync_topic_to_feishu`（触发审批确认后写入飞书）

### 集成
- 完全使用已有 data_foundation_tools，无需新工具
- `sync_topic_to_feishu` 在 `interrupt_on` → 用户审批后才写入飞书

---

## 设计三：xhs-decision 升级（更新现有 skill）

### 新增功能

**5种工作模式**（原3种扩展）：
- A 初始化：建目录骨架 + `我的当前状态.md`
- B 更新状态：读状态文件→听用户→写各层文件（默认模式）
- C 决策立案：`/决策立案` 触发，同时改4个文件
- D 结果回填：`/结果回填` 触发，同时改4个文件
- E 状态画像：`/状态画像` 触发，生成新快照

**概念炼出规律升格标准**（进 `02_规律/` 的门槛）：
- 在3次以上事实里出现过
- 能解释多个 `01_事实/` 条目
- 对下一步有明确指导作用
- 满足3条中2条才能升格，否则先在 `04_待解/` 用「暂定概念」标签

**来源标签体系**：
- `[AI推测]` / `[AI结论]` / `[AI元记录]`
- `[AI暂定概念 YYYY-MM-DD]`
- `[结果回填 YYYY-MM-DD]`
- `[修正 YYYY-MM-DD]`（追加，不覆盖原段）

**无隐私模式**（用户明确不要）

### 落盘路径
`/root/.dbs/decisions/{project_name}/`（容器内可写路径，已在 FilesystemPermission 中配置）

> ⚠️ 容器重启后 `/root/.dbs/` 数据会丢失，重要决策记录应配合 `/xhs-save` 调用 `save_session_snapshot` 做数据库备份

---

## 集成修复清单

1. ✅ xhs-positioning 增加「用户提出具体商业问题 → 用 `/xhs-diagnosis`」的路由
2. ✅ xhs-content-system Phase 1 加数据充足性前置检查
3. ✅ xhs-content-system Phase 4 说明 sync_topic_to_feishu 触发审批弹窗
4. ✅ xhs-decision 无隐私模式，注明容器重启数据丢失的备份建议
