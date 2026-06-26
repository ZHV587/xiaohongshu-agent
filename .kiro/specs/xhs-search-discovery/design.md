# Design Document: xhs-search-discovery(搜索发现 + 选择性采集)

## Overview

出选题的**第一步是搜索**。本 spec 把"搜索"从"只查本地 Postgres 底座"扩展为**双路并行召回**:本地已收集内容 + 线上小红书实时内容(红狐 API)。两路结果在面板上以**精致卡片**展示;线上结果用户**勾选「采纳收录」**后,才**一步写入我们的 Postgres(权威源)+ 同步飞书爆款采集库(镜像)**,并把互动数接成效果指标(复用 feishu-performance-metrics 框架)。

本 spec 是"搜索发现 + 选择性采集"的**独立能力**,不耦合出选题的证据链(EvidencePackage);出选题如何消费这些数据是下一步。

调研已全部完成(API 实测、字段核对、根因定位、前端机制、设计语言),无遗留技术未知点。

## 自审结论(关键修正,已纳入本设计)

对初稿做了一轮批判性自审,发现并修正以下问题(诚实记录,含一处自审自身的误判):

- **A〔高·真硬伤,已修〕本地检索不吐细致字段**:`search_resources`/`semantic_search_resources` 经 `rank_evidence` 只返回 `resource_id/title/summary/score/metadata`(metadata 仅 `type/visibility/source_updated_at/indexed_at`),**不含 `content_json` 的封面链接/互动明细/话题标签**。即使本地补全了库(Component 1),本地卡片仍拿不到细致内容。→ 新增**发现专用**本地检索(Component 2'),复用召回后 hydrate `content_json` 输出细致卡片字段;**不动** `rank_evidence`/`EvidencePackage` 证据链(出选题下一步仍用旧路径)。
- **B〔自审误判,维持原设计〕采纳路径**:初稿曾考虑"前端直连 internal API 落库"以省 token。**自审推翻**:`README` 架构铁律——"飞书写操作不经 frontend business API,由 Agent tools 发起并经 HITL 确认";`internal-client.ts` 先例仅用于**读/配置/鉴权**(chats/uat/status/config/health),不可用于业务写。→ 维持 `submitText → agent → adopt_online_notes 工具 → 飞书写经 HITL`;仅优化:回传**精简字段**(非全文)、前端把该回传消息渲染为简洁动作 chip(不露裸 JSON)。
- **C〔中·真问题,已修〕跨源去重**:同一笔记可能同时存在 `feishu_base_record`(本地已收录)与 `xhs_online_note`(线上),检索/卡片会重复。→ 以 `note_url`(原文链接)为跨源自然键去重;**本地优先**,线上结果若已在本地则标「已收录」且不可再采纳。
- **D〔中·真问题,实现与初稿不同(据实)〕飞书表去重**:初稿设想"`base +record-search` 按原文链接查存量→命中 update"。**实现时未采用**:代码库无证据表明 lark-cli v1.0.58 支持 `record-search`/`record-update`(只验证过 `record-create`/`record-list`/`table-list`),不愿凭未验证能力下手。**实际做法**:用 Postgres mapping `system="feishu_collect", external_type="xhs_note", external_id=note_id` 作幂等键——adopt 编排在写飞书前查该 mapping,已同步则跳过(`feishu_synced="skipped"`),未同步则 `record-create` 后回写该 mapping。**能保证"我方重复采纳不产生飞书重复行"**;**未覆盖**飞书侧由其它途径(如官方采集)已存在的同链接行的去重——那需 record-search 能力,留待核实 lark-cli 后再加。诚实标注此边界。
- **E〔已验证非问题〕ToolMessage 序列化**:LangGraph `msg_content_output` 对非 str/list 返回值做 `json.dumps(..., ensure_ascii=False)`,前端 `JSON.parse` 可直接解析(现有 `read_xhs_data` 返回 dict + 前端 `extractRowCount` JSON.parse 已在生产验证)。→ 工具返回 dict 即可,无需手工 dumps。
- **NEW〔中·真问题,已修〕采集库表 id 与草稿表不同**:`FEISHU_BITABLE_TABLE_ID` 是用户配置的**草稿/选题主表**(`sync_copy/topic/diagnosis` 写它);爆款采集库是 `tbl24vSVeLvz45ig`(§8 metrics 白名单)。二者不同源,写采集库须用**独立配置键** `FEISHU_BITABLE_COLLECT_TABLE_ID`,默认 `tbl24vSVeLvz45ig`,不可复用草稿表键。
- **F〔低·实现时细化〕卡片视觉规格**(间距/字号/移动端/暗色)留待实现细化,不阻塞设计。
- **G〔高·真硬伤,已修〕搜索卡片接在死渲染路径(实测发现)**:初稿前端通道事实写错(见上),把 `SearchCards` 接到了 `tool-calls.tsx` 的 `<ToolResult>`,而 `ToolResult` 在 `groupMessages` 架构下永不被渲染 → 搜索结果退化成 `ThinkingAura` 的普通工具步骤,卡片完全不显示(选题卡因走 ai 文本的 ` ```xhs_topics ``` ` 代码块,是活路径,所以能显示——正好对照印证)。**只过构建/lint 抓不到,是运行期渲染分发问题**。→ 修复:抽出**工具渲染注册表** `web/src/lib/tool-render.tsx`(`TOOL_RENDERERS` + `resolveToolRender` + `ToolResultCards`)作"每个工具怎么展示"的唯一事实源;`AssistantMessage` 用 `ToolResultCards` 从 `precedingTools[].result` 渲染富卡片(活路径,不受 `isThinkingOnly` 限制);`ThinkingAura` 改读 `resolveToolRender`(搜索工具 `aura:"hidden"` 且有 `card`,故不在思考链重复);移除 `ToolResult` 里的死分支。**教训**:前端渲染链结论必须读 `groupMessages` 实际分发后才能下,不能凭"ToolMessage→ToolResult"想当然。

## 调研事实(已验证)

- **红狐 API 可用**:`POST https://redfox.hk/story/api/xhs/search/search`,头 `X-API-KEY`,入参 `{keyword,pageNum,pageSize,startDate,endDate,source}`,返回 `{code:2000,data:{articles[],relatedSearches,latestHotArticles}}`。每条笔记含 `title/desc/authorId/authorNickname/authorFans/createTime/shareInfoLink/cover/interactiveCount/likedCount/collectedCount/commentsCount/sharedCount/topicsName/relevanceScore/popularityScore/recencyScore/totalScore`。互动收录门槛 1000+,每日 7 点更新昨日数据,仅近 30 天。
- **本地数据缺口的根因**:`tools/feishu_bitable.py` 的 `_EXCLUDE_COLUMN_KEYWORDS`(含 `封面/链接/网址/域名/图片/附件/...`)在同步时**主动丢弃**了封面/原文链接等列。lark-cli `record-list` 实际返回 **57 个业务列(完整,无漏)**,缺的 6 列是 `not_support` 系统设置列(无值)。
- **封面图取法**:`封面`(附件)是飞书附件对象 `[{file_token,...}]`(需换 URL、有时效);但 `封面链接`(文本)是**小红书 CDN 直链** `http://sns-webpic-qc.xhscdn.com/...`(公网稳定,拿来即用)。→ 封面用 `封面链接`,绕开附件对象。`原文链接` 是 `[查看原文](http://xhslink.com/o/...)`(markdown,提取 URL)。
- **前端数据通道(已据实修正)**:面板渲染链是 `ChatTimeline` → `groupMessages()` → `AssistantMessage`。**关键事实**:`groupMessages` 把所有 tool 消息**折叠进 `group.toolCalls[].result`**,`AssistantMessage` 只接收 `group.aiMessage`(永远是 `ai` 类型),因此 `isToolResult`/`<ToolResult>` 分支**在本 UI 永不触发(死路径)**。→ 富工具卡片**必须从 `precedingTools[].result` 渲染**(在 `AssistantMessage` 内),而非 `ToolResult`。`ThinkingAura`(思考链)默认把每个非 skill 工具渲染成一步,故有专属卡片的工具(搜索)要从思考链里排除。agent 文本只留摘要。
  ⚠️ 初稿这条曾错写成"`ai.tsx` 的 `isToolResult` → `<ToolResult>`",据此把 `SearchCards` 接到了死路径 → 搜索卡片不显示(见自审 G)。
- **卡片动作机制**:卡片按钮经 `useThreadActions().submitText` 发消息给主控继续(选题卡选择即此模式)。
- **设计语言**:暖色系 `coral`(珊瑚红)/`oats`(燕麦)/`charcoal`,圆角 `rounded-xl/2xl`,`shadow-xs`,framer-motion 动效,skeleton-shimmer。已有"小红书笔记卡片"(PhoneSimulator)与"飞书写入卡片"(RightInspector)先例。
- **飞书写工具现状**:`feishu_actions.py` 的 `sync_*_to_feishu` 全写草稿/选题/诊断表,**没有**写爆款采集库的工具。

## Architecture

```mermaid
graph TD
    U[用户给关键词] --> M[主控 Agent]
    M -->|本地一路| L[search_local_note_cards 工具<br/>召回 + hydrate content_json 细致字段]
    M -->|线上一路| O[search_xhs_online 工具<br/>红狐 API]
    L --> DD{跨源去重<br/>按 note_url}
    O --> DD
    DD --> TM[ToolMessage 结构化结果<br/>本地组 + 线上组(标记已收录)]
    TM -->|前端按工具名渲染| FE[面板:细致卡片网格]
    M -.AI 文本只留摘要.-> FE
    FE -->|勾选线上卡 → submitText 回传精简 payload| M
    M -->|采纳收录(单动作)| A[adopt_online_notes 工具]
    A -->|入库 权威| PG[(Postgres: xhs_online_note + measured_by 效果指标)]
    A -->|同步 镜像 · HITL| FB[(飞书爆款采集库 FEISHU_BITABLE_COLLECT_TABLE_ID<br/>默认 tbl24vSVeLvz45ig)]
```

判据:搜索=动作=**工具**;细致结果走 **ToolMessage 数据通道**(不经 agent 文本);采纳=**agent 工具**(入库+飞书原子化,飞书写经 HITL——遵 README 铁律"飞书写不经 frontend business API");卡片交互=`submitText` 回传选择(精简字段)。本地卡片由**发现专用**检索 hydrate `content_json` 取细致字段,**不复用** `rank_evidence` 证据链路径。

## Components and Interfaces

### Component 1:本地数据补全(收窄过滤 + 回填)

**Purpose**:让本地已收集内容也有封面/原文链接等细致字段,与线上卡片字段对齐。

- **收窄 `_EXCLUDE_COLUMN_KEYWORDS`**:移除 `封面/链接/网址/域名/图片`,放行封面链接/原文链接/封面链接/图片链接/视频链接/域名等文本字段。**保留过滤**真正无用项:`附件`(附件对象,有 file_token 替代直链)、`提示词`、`二维码`、`头像`、`logo`、`trace`、`⚙️`/`设置`(not_support 系统列)。
- **封面归一化**:落库时把 `封面链接` 作为统一封面 URL 字段;`原文链接` 提取 markdown 中的 URL。
- **存量回填**:对现有 `feishu_base_record` re-sync(经已修好的 bot 同步链路),补齐放行字段。幂等(按 external_id)。**已执行**:re-sync 570 行,补到 205 条封面链接 / 457 条原文链接(并非每条都有这两列)。

**约束**:不改飞书侧;只改我们同步时的字段过滤 + 回填。

### Component 2':发现专用本地检索 `search_local_note_cards`(真问题A 修复)

**Purpose**:为发现面板提供**细致**本地卡片字段,与线上卡片对齐。**独立于** `rank_evidence`/`EvidencePackage` 证据链(那条路径保持现状,供出选题下一步使用)。

**Interface**:
```python
@tool
def search_local_note_cards(keyword: str, limit: int = 12, config=None) -> dict:
    """检索本地已收录笔记,返回细致卡片字段(封面/互动/标签),用于发现面板展示。"""
```
- **召回**:复用现有 Meili/语义召回拿到 readable `resource_id` 列表(经租户 + 权限裁决,沿用 `search_resources` 的 over-fetch + PG 权限后置)。
- **hydrate**:对命中的 resource 读 `content_json.fields`,映射出统一卡片形状(`cover_url` 取归一化后的 `封面链接`、`note_url` 取 `原文链接`、互动数取点赞/收藏/评论/转发列、`tags` 取话题标签列、`author`/`author_fans`/`created_at`)。
- **去重**:返回前按 `note_url` 内部去重(防同一笔记多条记录)。
- 返回 `source="local"`,字段形状与线上完全一致(见 Data Models)。
- **不动** `search_resources`/`semantic_search_resources`/`rank_evidence` 的返回结构与 EvidencePackage 消费方。

### Component 2:线上检索工具 `search_xhs_online`

**Interface**:
```python
@tool
def search_xhs_online(keyword: str, days: int = 7, page_size: int = 20, config=None) -> dict:
    """实时搜索小红书热门笔记(红狐 API)。返回结构化笔记列表用于面板卡片展示;不落库。"""
```
- 调 `https://redfox.hk/story/api/xhs/search/search`,`X-API-KEY` 取自 `REDFOX_API_KEY` 环境变量。
- `startDate = today - days`。
- 返回**精简对齐字段**(供 ToolMessage 渲染,控上下文):每条 `note_id/title/summary(desc截断)/author/author_fans/cover_url/note_url/likes/collects/comments/shares/interactive/created_at/tags/scores{relevance,popularity,recency,total}`;附 `related_searches`。
- **不含全文**(desc 截断为摘要),控制 ToolMessage 体积。
- **降级**:超时/非 2000/网络异常 → 返回 `{ok:False, reason}`,主控明说"线上检索暂不可用,仅展示本地结果",不阻断。
- HTTP 同步调用:容器已设 `LANGGRAPH_ALLOW_BLOCKING=true`,不被 blockbuster 拦。

### Component 3:数据通道 + 前端细致卡片

**数据通道**:本地/线上检索工具的结构化结果作为 **ToolMessage** 进入消息流。前端经**工具渲染注册表** `web/src/lib/tool-render.tsx`(`TOOL_RENDERERS`:`search_xhs_online`/`search_local_note_cards` → `aura:"hidden"` + `card: SearchCards`)在 `AssistantMessage` 用 `ToolResultCards` 从 `precedingTools[].result` 渲染细致卡片网格(见自审 G)。`tool-display.ts` 仅保留 `ToolCalls` 进行中/完成 chip 文案,**不渲染卡片**。**主控 AI 文本只输出摘要**(如"本地 N 条 + 线上 M 条,已在面板展示,勾选要收录的"),不重复全量数据。

**跨源去重(真问题C)**:面板合并本地组 + 线上组前,按 `note_url`(原文链接)归一化做跨源去重。**本地优先**:线上结果若其 `note_url` 已存在于本地组,则该线上卡标「📚已收录」徽章、禁用采纳勾选(不重复入库)。去重在工具层(线上工具可选携带"已在本地"标记)或前端合并层完成;以工具层为准(线上工具返回时即比对本地 `note_url` 集合,打 `already_local: bool`)。

**卡片视觉**(沿用 coral/oats 设计语言):
- 图文横排:左 3:4 封面(`cover_url`/`封面链接`;无图给 oats 占位),右信息区。
- 标题(粗体两行截断)、`@博主 · 粉丝数`、来源徽章(本地「📚已收录」/ 线上「🔥实时·N天前」)。
- 互动 chips:🔥互动(coral 高亮)/👍赞/⭐藏/💬评/↗转。
- 话题标签 pills(oats/sky 底)。
- 评分徽章(线上):相关性/热度/时效(复用红狐三维)。
- `查看原文 ↗`(note_url)。
- **操作区**:**每张卡**(本地+线上)右下角有「✨出选题」按钮(基于这一篇出 1 个选题,见「出选题衔接」);**仅线上卡**额外有勾选框 + `采纳收录`(coral 主按钮),`already_local`/已入库显示灰标「已收录」并禁用采纳。
- 分组:`📚 我们已收录(N)` + `🔥 线上实时发现(N)`,各带计数;加载 skeleton-shimmer;hover 微抬升。
- 批量:线上组顶部「全选 / 采纳选中(k)」。

**勾选 → 采纳**:用户勾选后点「采纳选中」→ 前端 `submitText` 回传**选中笔记的精简 payload(JSON,仅卡片级字段、不含全文)** → 主控调 `adopt_online_notes`。前端 `human.tsx` 的 `summarizeCardAction` 识别此类动作回传(含 ```json``` 块),渲染成简洁动作 chip(「🍠 采纳收录 N 条线上笔记」/「✨ 基于选中的笔记出选题」),**不暴露裸 JSON**(数据照传给 agent,仅显示层折叠)。**采纳路径取 agent 工具 + HITL**(非前端直连 internal API)——遵 README 架构铁律:飞书写操作由 Agent tools 发起并经 HITL 确认,`internal-client.ts` 仅用于读/配置/鉴权。

### Component 4:采纳收录工具 `adopt_online_notes`(入库 + 飞书一体)

**Interface**:
```python
@tool
def adopt_online_notes(notes: list[dict], sync_feishu: bool = True, config=None) -> dict:
    """把用户选中的线上笔记收录:写 Postgres(权威)+ 同步飞书爆款采集库(镜像)。幂等。"""
```
**流程**(每条笔记):
1. **入 Postgres**:`upsert_resource(type="xhs_online_note", ...)`,`content_json` 存全部线上字段;`mapping` 用 `system="redfox", external_id=note_id` 保证**幂等去重**(同一笔记重复采纳更新不堆叠)。owner = 当前用户。走 outbox(meili 索引 + 排队 embedding → 进语义检索复利)。
2. **接效果指标**:互动数(likes/collects/comments/shares)→ `save_performance_metric_resource(target=该 resource)`(复用 §8 框架,幂等)。
3. **同步飞书爆款采集库**(`sync_feishu=True` 时):`create_online_note_record` 写 `FEISHU_BITABLE_COLLECT_TABLE_ID`(默认 `tbl24vSVeLvz45ig`,**独立于草稿表** `FEISHU_BITABLE_TABLE_ID`),列映射(标题/正文/点赞数/收藏数/评论数/转发数/博主/发布时间/封面链接/原文链接/话题标签/采集平台=线上实时);**去重(真问题D,实际做法)**:adopt 编排写飞书前查 `feishu_collect` mapping(external_id=note_id),已同步→跳过,未同步→ `record-create` 后回写 mapping。`record-search`/`record-update` 因 lark-cli 能力未核实**未采用**(见自审 D);飞书写由整工具 `adopt_online_notes` 经 `interrupt_on` HITL 审批。
4. **权威性**:数据库先写成功;飞书失败保留库记录并明确报告同步失败(沿用既有"数据库权威、飞书镜像"原则)。

**返回**:每条 `{note_id, adopted: True, resource_id, feishu_synced: bool|"skipped"|"failed"}`,供前端把卡片标记「已收录」;整体附 `next_step` 引导出选题。

### Component 5:飞书爆款采集库写入 `create_online_note_record`(普通函数,非 @tool)

新增于 `tools/feishu_actions.py`(供 `adopt_online_notes` 编排调用,HITL 在 adopt 工具边界统一拦):
- 目标表:`FEISHU_BITABLE_COLLECT_TABLE_ID`(爆款采集库,默认 `tbl24vSVeLvz45ig`)。**不复用** `FEISHU_BITABLE_TABLE_ID`。配置键加入 `config-store.ts` 白名单与飞书配置页。
- 列映射:标题/正文/博主/封面链接/原文链接/话题标签/发布时间/采集平台 + 点赞数/收藏数/评论数/转发数(与 §8 `COLUMN_TO_METRIC` 对齐);列名经服务器只读探测确认与采集库实际列一致。
- 只负责 `base +record-create` 写;**去重在 adopt 编排层**按 `feishu_collect` mapping 保证(见 Component 4)。
- `lark-cli base` 命令,经 lark_cli wrapper;采纳是用户交互 → **用户 UAT 身份**(非 bot)。

## Data Models

### 线上/本地笔记(工具返回 / 前端卡片 / 采纳 payload 统一形状)
```python
{
  "note_id": str, "title": str, "summary": str,           # desc 截断
  "author": str, "author_fans": int,
  "cover_url": str, "note_url": str,                       # note_url=原文链接,跨源去重自然键
  "likes": int, "collects": int, "comments": int, "shares": int, "interactive": int,
  "created_at": str, "tags": list[str],
  "scores": {"relevance": float, "popularity": float, "recency": float, "total": float},  # 线上专有;本地省略
  "source": "online" | "local",     # 本地由 search_local_note_cards hydrate content_json 得到
  "already_local": bool             # 线上结果:其 note_url 是否已在本地(C 去重);True → 卡片标「已收录」、禁采纳
}
```
本地与线上字段对齐;本地 `cover_url` 取 `content_json` 的归一化 `封面链接`,无图时前端 oats 占位。

### `xhs_online_note` resource(落库)
- `type="xhs_online_note"`,`content_json` = 上述全部字段 + 原始红狐响应子集 + `note_url`(跨源去重键)。
- `mapping`: `system="redfox"`, `external_type="xhs_note"`, `external_id=note_id`(幂等键);同步飞书成功后另加一条 `system="feishu_collect", external_type="xhs_note", external_id=note_id`(**按 note_id**,作飞书侧"我方是否已同步"的幂等标记;不存飞书自增 record_id,因未用 record-search/update,见自审 D)。
- 互动数 → `performance_metric` + `measured_by` 边(§8 口径)。

## Correctness Properties

### Property 1:本地字段补全
收窄过滤后,re-sync 的 `feishu_base_record.content_json.fields` 含 `封面链接`/`原文链接`;仍不含纯噪声(附件对象/提示词/⚙️系统列)。
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2:线上检索瞬态、不落库
`search_xhs_online` 仅返回结果,**不写** Postgres/飞书;失败时降级为"仅本地",不抛错中断。
**Validates: Requirements 2.1, 2.4, 2.5**

### Property 3:细致数据走 ToolMessage,不灌 agent 文本
搜索结果经 ToolMessage 渲染;主控 AI 文本不重复全量笔记 JSON(只摘要)。
**Validates: Requirements 3.1, 3.4**

### Property 4:采纳才落库(选择性)
仅当用户勾选并触发 `adopt_online_notes` 时才写库/飞书;未采纳的线上笔记不留痕。
**Validates: Requirements 4.1, 4.2**

### Property 5:采纳幂等(双侧)
对同一 note_id 采纳 N 次 ⟹ Postgres 恰 1 条 `xhs_online_note` + 1 条 `measured_by` + 飞书采集库恰 1 条(adopt 编排按 `feishu_collect` mapping:已同步则跳过 create,不新建)。
**Validates: Requirements 4.3, 5.3**

### Property 6:跨源去重(真问题C)
线上结果若 `note_url` 已在本地命中 ⟹ `already_local=True`,前端禁用采纳;面板不出现同一 `note_url` 的本地+线上重复卡。
**Validates: Requirements 2.6, 3.5**

### Property 7:入库 + 飞书一体,数据库权威
采纳 = 入 Postgres + 同步飞书一个动作;数据库先成功,飞书失败保留库记录并报告。
**Validates: Requirements 4.4, 5.4**

### Property 8:效果指标接通
采纳的线上笔记互动数 → `performance_metric`,被 `rank_evidence` 消费(复用 §8)。
**Validates: Requirements 4.5**

### Property 9:本地卡片细致字段(真问题A)
`search_local_note_cards` 返回含 `cover_url`/互动/`tags`(由 `content_json` hydrate);`search_resources`/`semantic_search_resources`/`rank_evidence`/EvidencePackage 返回结构**不变**(证据链不被破坏)。
**Validates: Requirements 1.4, 3.2**

### Property 10:卡片视觉一致
本地/线上卡片同一组件、沿用 coral/oats token、含封面/互动/标签/来源徽章/(线上)采纳按钮;本地无封面时优雅占位。
**Validates: Requirements 3.2, 3.3, 6.1, 6.2**

## Error Handling

- **红狐 API 失败/超时**:降级为仅本地结果,主控明说线上不可用,不抛错。
- **关键词为泛词(可选)**:红狐 skill 建议"泛词先推细分词";第一步可选不实现(直接搜),作为范围外增强。
- **采纳单条失败**:逐条 try,失败计入返回 errors,不影响其余;前端只把成功的标「已收录」。
- **飞书同步失败**:保留 Postgres 记录,卡片标「已入库·飞书同步失败」。
- **封面 URL 失效**:CDN 直链失效 → 前端图片 onError 显示 oats 占位。
- **幂等**:re-sync 与采纳均按 `note_url`/external_id 幂等,重复操作不堆叠(Postgres + 飞书双侧)。

## Testing Strategy

- **Unit**:
  - `_filter_fields` 收窄后:放行封面链接/原文链接,仍过滤附件/提示词/⚙️(`test_feishu_bitable`)。
  - `search_local_note_cards`:hydrate `content_json` → 细致字段映射正确、按 note_url 内部去重;**断言 `rank_evidence`/`search_resources` 返回结构未变**(回归保护证据链)。
  - `search_xhs_online`:mock 红狐响应 → 字段映射正确;非 2000/超时 → 降级 `ok=False`;`already_local` 按本地 note_url 集合正确标记。
  - `adopt_online_notes`:幂等(同 note_id 调 2 次 = 1 资源 1 边)、入库+效果指标、飞书失败不回滚库。
  - `create_online_note_record`:列映射正确(标题/封面链接/原文链接/点赞数...);默认写 `tbl24vSVeLvz45ig`、缺 app_token 报错。
  - `adopt_online_notes` 编排:`feishu_collect` mapping 幂等(已同步→skipped、未同步→create 后回写 mapping)。
- **Property-based(hypothesis)**:任意红狐响应形状 → 映射不抛错、数值非负;采纳幂等不变量;跨源去重不变量(同 note_url 不出双卡)。
- **前端**:搜索卡片从 `precedingTools[].result` 在 `AssistantMessage` 渲染(真问题G);勾选 → submitText 精简 payload 正确;`already_local` 卡禁用采纳;每卡「✨出选题」回传单篇。
- **集成(服务器,部分已跑/部分待浏览器验证)**:本地补全 re-sync 后封面/原文链接入库(✅570/205/457);本地检索 → 细致卡片(✅工具层);线上检索 → 卡片 → 采纳 → 库+飞书(⚠️卡片渲染与采纳待浏览器实跑)。

## 受影响文件清单

| 文件 | 改动 | 类型 |
|---|---|---|
| `tools/feishu_bitable.py` | 收窄 `_EXCLUDE_COLUMN_KEYWORDS`;封面链接/原文链接归一化 | 改 |
| `tools/redfox_search.py` | 新增 `search_xhs_online` 工具(红狐 API)+ `already_local` 跨源比对 | 新增 |
| `data_foundation/local_cards.py` | 新增 `search_local_note_cards`(召回 + hydrate content_json,真问题A) | 新增 |
| `data_foundation/online_notes.py` | 新增 `adopt_online_notes_resource`(入库 + 效果指标,幂等) | 新增 |
| `tools/feishu_actions.py` | 新增 `create_online_note_record`(写采集库列映射;去重由 adopt 编排按 mapping 保证,**未用** record-search/update,见下) | 改 |
| `tools/online_adopt.py` | 新增 `adopt_online_notes` 工具(编排入库+效果指标+飞书镜像,feishu_collect mapping 幂等);返回 `next_step` 衔接出选题 | 新增 |
| `agent.py` | 注册 `search_xhs_online`/`adopt_online_notes`;`search_local_note_cards` 在 data_foundation/tools;`interrupt_on` 加 `adopt_online_notes` | 改 |
| `prompts.py` | §6.5 发现式搜索 + 双源出选题 + 采纳衔接;§6/§5 约定 | 改 |
| `.agents/skills/topic-content,xhs-planning,xhs-content-system/SKILL.md` | 出选题只展示不落库、选中才存;单篇原文→单选题快路;双源(线上趋势) | 改 |
| `.env` / docker-compose | `REDFOX_API_KEY` + `FEISHU_BITABLE_COLLECT_TABLE_ID`(默认 tbl24vSVeLvz45ig)+ 容器注入(env_file 透传) | 改 |
| `web/src/lib/server/config-store.ts` | 白名单加 `FEISHU_BITABLE_COLLECT_TABLE_ID` | 改 |
| `web/src/components/thread/history/FeishuConfigPage.tsx` | 采集库表 id 配置项 | 改 |
| `web/src/lib/tool-display.ts` | 搜索/采纳工具的进行中/完成文案(注:卡片渲染**不**走 tool-display,见 ai.tsx) | 改 |
| `web/src/components/thread/messages/search-cards.tsx` | 新增细致搜索卡片(本地/线上分组、勾选采纳、已收录禁用、每卡「✨出选题」) | 新增 |
| `web/src/lib/tool-render.tsx` | **新增工具渲染注册表**(`TOOL_RENDERERS`+`resolveToolRender`+`ToolResultCards`):每个工具的思考链/卡片/进行中表现的唯一事实源;已覆盖全业务工具(检索/落库/同步/采纳)中文文案,未注册工具优雅降级为中文"已完成一步处理"(不露英文名) | 新增 |
| `web/src/components/thread/messages/ai.tsx` | **真问题G 修复**:`AssistantMessage` 用 `ToolResultCards` 从 `precedingTools[].result` 渲染搜索卡片(活路径);`ThinkingAura` 改读 `resolveToolRender` | 改 |
| `web/src/components/thread/messages/human.tsx` | `summarizeCardAction`:采纳/出选题回传渲染成动作 chip,不露裸 JSON | 改 |
| `web/src/components/thread/messages/tool-calls.tsx` | 移除死的 `SearchCards`/`ToolResult` 搜索分支 | 改 |
| 存量回填 | 经 bot 同步链路 re-sync 570 行补封面/原文链接(已跑:205 封面 / 457 原文) | 已执行 |
| tests(后端 + 前端) | 上述单元/属性/集成测试 | 新增/改 |

## Dependencies

- 红狐 API(REDFOX_API_KEY)。复用:§8 效果指标框架(save_performance_metric)、lark_cli(bot/UAT)、upsert_resource 幂等、前端 ToolMessage/tool-display 渲染、coral/oats 设计系统。
- 无新第三方依赖(HTTP 用现有 httpx/urllib);无 schema 迁移(`xhs_online_note` 复用 resources 表)。

## 出选题衔接(已实现的扩展,超出初稿"独立能力"范围)

初稿把出选题列为"范围外/下一步";实现中按用户要求做了衔接,据实记录:

- **采纳即可出选题(零额外开发)**:采纳的 `xhs_online_note` 走 outbox 进 meili/embedding,落库即成为 `semantic_search_resources`/`search_resources`/`rank_evidence` 的证据(visibility=team 可读、带 `performance_metric` 互动分)。所以"采纳后出选题就能引用线上内容"在结构上天然通。
- **双源出选题(B,选定)**:出选题时主控可额外调 `search_xhs_online(方向)` 拉线上实时热门作**趋势信号**(瞬态、不落库);正式 evidence 仍须库内 `resource_id`,纯线上趋势的选题注明 `(线上实时:note_url)` 并提示采纳后才作正式依据。守"采纳才落库 + 依据须 resource_id"两铁律。
- **单篇原文→单选题(用户指定的最短路)**:搜索卡片每张加「✨出选题」按钮 → `submitText` 回传这一篇(本地带 resource_id、线上带 note_url)→ topic-content 走"单篇→1 选题"快路,分析这一篇产 1 个选题。
- **出选题不自动落库(用户铁律,已修)**:topic-content/xhs-planning/xhs-content-system 三技能改为"出选题只展示,**选中才存**那一个",杜绝 3~5 个垃圾选题被无差别落库。与"采纳才落库"同源。

## 范围外(仍未做)

- 选题卡上结构化展示"线上趋势信号区块"+ 从选题卡一键采纳那条线上笔记(需扩 `xhs_topics` 协议 + 改 topic-cards.tsx)。
- 飞书侧"他途已存在同链接行"的去重(需核实 lark-cli `record-search` 能力)。
- 泛化词先推细分词的交互增强;线上检索结果的自动定时采集(本步只做对话触发的手动采纳)。
- **浏览器端实跑验证**:搜索卡片/出选题按钮的真实渲染与交互(真问题G 修复后)尚需在 `124.221.173.80:9091` 用眼确认,不能只凭构建/lint。
