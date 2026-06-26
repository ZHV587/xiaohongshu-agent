# Requirements Document

特性:xhs-search-discovery(搜索发现 + 选择性采集)

## Glossary

- **本地已收录内容**:已同步进 Postgres 数据底座的笔记(来源主要为飞书爆款采集库),resource `type` 含 `feishu_base_record` 等。
- **线上实时内容**:经红狐 API(`redfox.hk`)实时检索到的小红书热门笔记,默认瞬态、不落库。
- **采纳收录(adopt)**:用户勾选线上笔记后触发的单动作——写 Postgres(权威)+ 同步飞书爆款采集库(镜像)+ 接效果指标。
- **细致卡片**:含封面、互动明细、话题标签、来源徽章的统一卡片形状(本地/线上共用)。
- **note_url**:笔记原文链接,作为跨源 / 跨系统去重的自然键。
- **HITL**:Human-In-The-Loop,飞书写操作经 `interrupt_on` 暂停由人工审批。
- **§8 框架**:feishu-performance-metrics 既有能力(`save_performance_metric_resource` + `measured_by` + `rank_evidence` 消费)。
- **UAT / bot 身份**:UAT=用户访问令牌(前端交互写飞书用);bot=应用机器人(自动同步用)。

## Introduction

出选题的第一步是"搜索"。本特性把搜索从"只查本地 Postgres 底座"扩展为**双路并行召回**:本地已收录内容 + 线上小红书实时内容(红狐 API)。两路结果以**精致卡片**在面板展示;线上结果由用户**勾选「采纳收录」**后,才**一步写入 Postgres(权威)+ 同步飞书爆款采集库(镜像)**,并把互动数接成效果指标(复用 feishu-performance-metrics 框架)。本特性是"搜索发现 + 选择性采集"的独立能力,不耦合出选题的证据链(EvidencePackage)。

铁律约束:飞书写操作由 Agent tools 发起并经 HITL 确认(不经 frontend business API);明文配置;根本性修复不打补丁;相关测试一并重写;中文为主场景。

## Requirements

### Requirement 1:本地已收录内容可作为细致卡片被检索

**User Story:** 作为创作者,我想在搜索时看到我们自己已收录的笔记的封面、互动数、话题标签等细致信息,以便和线上结果一致地评估。

#### Acceptance Criteria

1.1 WHEN 系统从飞书同步笔记到本地 THEN 系统 SHALL 保留 `封面链接`、`原文链接` 等文本字段(收窄 `_EXCLUDE_COLUMN_KEYWORDS`),不再丢弃。
1.2 WHEN 同步落库 THEN 系统 SHALL 把 `封面链接` 归一化为统一封面 URL 字段、从 `原文链接` markdown 提取 URL。
1.3 WHILE 收窄过滤生效 THE 系统 SHALL 仍过滤纯噪声项(附件对象、提示词、二维码、头像、logo、trace、⚙️/设置 等 not_support 系统列)。
1.4 WHEN 用户用关键词检索本地内容 THEN 系统 SHALL 通过 `search_local_note_cards` 返回含 `cover_url`、互动明细、`tags` 的细致卡片字段(由 `content_json` hydrate)。
1.5 IF 存量本地记录缺少放行字段 THEN 系统 SHALL 提供回填能力 re-sync 现有记录补齐字段,且按 external_id 幂等。

### Requirement 2:线上实时检索(红狐 API),瞬态不落库

**User Story:** 作为创作者,我想用关键词实时搜到小红书线上热门笔记,以便发现本地库里还没有的新内容。

#### Acceptance Criteria

2.1 WHEN 用户给出搜索关键词 THEN 系统 SHALL 通过 `search_xhs_online` 调用红狐 API 返回结构化笔记列表用于面板展示。
2.2 THE 系统 SHALL 把每条线上笔记映射为统一卡片形状(note_id/title/summary/author/author_fans/cover_url/note_url/互动数/created_at/tags/scores)。
2.3 THE 系统 SHALL 对线上摘要做截断(不返回全文)以控制 ToolMessage 体积。
2.4 WHEN 线上检索执行 THEN 系统 SHALL NOT 写入 Postgres 或飞书(线上结果默认瞬态)。
2.5 IF 红狐 API 超时、返回非 2000 或网络异常 THEN 系统 SHALL 降级返回 `{ok:False, reason}` 并由主控明示"线上检索暂不可用,仅展示本地结果",不抛错中断。
2.6 WHEN 某条线上笔记的 `note_url` 已存在于本地结果 THEN 系统 SHALL 标记其 `already_local=True`。

### Requirement 3:双路结果以细致卡片在面板展示,数据不灌 agent 文本

**User Story:** 作为创作者,我想在面板上以好看的卡片网格看到本地组与线上组,以便快速浏览和选择。

#### Acceptance Criteria

3.1 WHEN 检索工具返回结果 THEN 系统 SHALL 经 ToolMessage 数据通道把结构化结果送达前端,由 `@/lib/tool-display` 按工具名渲染细致卡片。
3.2 THE 卡片 SHALL 展示封面、标题、博主+粉丝数、互动 chips(赞/藏/评/转)、话题标签、来源徽章(本地「📚已收录」/ 线上「🔥实时」)、(线上)三维评分。
3.3 THE 系统 SHALL 用同一卡片组件渲染本地与线上结果,沿用 coral/oats 设计语言;本地无封面时优雅 oats 占位。
3.4 WHEN 检索结果在面板展示 THEN 主控 AI 文本 SHALL 只输出摘要(条数 + 引导语),不重复全量笔记 JSON。
3.5 WHEN 面板合并本地组与线上组 THEN 系统 SHALL 按 `note_url` 跨源去重,本地优先;`already_local=True` 的线上卡 SHALL 标「已收录」且禁用采纳勾选。

### Requirement 4:线上结果用户选择性采纳,采纳=入库+飞书一体

**User Story:** 作为创作者,我想自己勾选要保留的线上笔记再收录,而不是全部自动入库,以保持库的质量。

#### Acceptance Criteria

4.1 WHEN 用户勾选线上卡并点「采纳选中」THEN 前端 SHALL 通过 `submitText` 回传选中笔记的精简 payload(卡片级字段,不含全文),由主控调 `adopt_online_notes`。
4.2 WHILE 用户未采纳 THE 系统 SHALL NOT 为该线上笔记留下任何 Postgres/飞书痕迹。
4.3 WHEN 采纳一条线上笔记 THEN 系统 SHALL upsert 一条 `xhs_online_note` resource(`content_json` 存全部线上字段 + note_url),mapping `system="redfox", external_id=note_id` 保证幂等,走 outbox(meili 索引 + 排队 embedding)。
4.4 WHEN 采纳执行 THEN 系统 SHALL 把入库与同步飞书作为**一个动作**(单按钮);数据库先写成功,飞书失败保留库记录并明确报告同步失败。
4.5 WHEN 采纳一条线上笔记 THEN 系统 SHALL 把其互动数接成 `performance_metric` + `measured_by` 边(复用 §8 框架),供 `rank_evidence` 消费。
4.6 WHERE 采纳是用户交互触发的飞书写 THE 系统 SHALL 使用用户 UAT 身份,并把飞书写纳入 `interrupt_on` HITL 审批。

### Requirement 5:同步飞书爆款采集库(独立表,自然键去重)

**User Story:** 作为创作者,我想采纳的线上笔记自动镜像到飞书爆款采集库,且不和飞书里已有的采集行重复。

#### Acceptance Criteria

5.1 THE 系统 SHALL 把采纳的线上笔记写入 `FEISHU_BITABLE_COLLECT_TABLE_ID`(默认 `tbl24vSVeLvz45ig`),不复用草稿/选题表 `FEISHU_BITABLE_TABLE_ID`。
5.2 THE 系统 SHALL 按列映射写入(标题/正文/点赞数/收藏数/评论数/转发数/博主/发布时间/封面链接/原文链接/话题标签/采集平台)。
5.3 WHEN 写飞书采集库 THEN 系统 SHALL 先用 `base +record-search` 按 `原文链接` 查存量:命中则 update 不新建,未命中则 create 后把飞书 `record_id` 回写 Postgres mapping(`system="feishu_collect"`),保证按 note_url 双侧幂等。
5.4 IF 飞书同步失败 THEN 系统 SHALL 保留 Postgres 记录并向用户报告"已入库·飞书同步失败"(数据库权威、飞书镜像)。
5.5 THE `FEISHU_BITABLE_COLLECT_TABLE_ID` SHALL 进入 web 配置白名单与飞书配置页,可由管理员明文配置。

### Requirement 6:卡片视觉与交互一致性

**User Story:** 作为创作者,我想卡片好看、操作直觉,以便高效完成发现与采纳。

#### Acceptance Criteria

6.1 THE 卡片 SHALL 沿用 coral/oats/charcoal 设计 token、rounded-xl/2xl、shadow-xs、加载 skeleton-shimmer、hover 微抬升。
6.2 THE 线上组 SHALL 提供「全选 / 采纳选中(k)」批量操作;已采纳/已收录的卡 SHALL 显示灰标「已收录」且不可重复采纳。
