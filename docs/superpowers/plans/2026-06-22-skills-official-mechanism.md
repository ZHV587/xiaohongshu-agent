# skills 机制改造为 deepagents 官方方式

日期:2026-06-22
状态:待批准

## 背景与根因

项目有 4 个真实 `SKILL.md`(`.agents/skills/` 下:topic-content、lark-base、lark-im、lark-shared),
但**没用官方 `create_deep_agent(skills=...)` 参数**,而是把 `/skills/` 挂成 CompositeBackend 的一个
route 让 agent 自己 `read_file`。问题:

- 官方 `SkillsMiddleware` 会把每个 skill 的 name/description/path 自动注入 system prompt
  (渐进式披露),让模型知道"有哪些 skill、何时读哪个"。这是 skill 机制的灵魂。
- 现状里 `MAIN_SYSTEM_PROMPT` 只字未提 `/skills/` 路径,agent 根本不知道这些文件存在 → 永不读取。
- 更直接的证据:`topic-content/SKILL.md` 与 `MAIN_SYSTEM_PROMPT` 内容**几乎逐字重复**(同样的
  检索顺序、xhs_topics/xhs_copy 协议、保存调用)。当初是"把 skill 内容手抄进 prompt"绕过了机制。
- 结果:`/skills/` route + 4 个 SKILL.md 是**死配置**,且与 prompt 双份维护,改一处忘另一处必漂移。

## 已验证的关键事实(服务器实测/读码坐实)

1. `create_deep_agent(skills=[...])` 把主 `backend` 传给 `SkillsMiddleware`,对 source_path 调
   `backend.ls()` 列子目录、每个子目录下载 `SKILL.md` 解析 frontmatter。
2. 服务器实测:`build_backend().ls("/skills/")` 经 CompositeBackend route 正确列出 4 个 skill 目录,
   `download_files(["/skills/topic-content/SKILL.md"])` 成功(content_len=5585)。**现有 backend route
   与官方 SkillsMiddleware 天然对接,`skills=["/skills/"]` 即可跑通,无需改 backend。**
3. 4 个 SKILL.md 的 frontmatter `name` 均与父目录名一致(官方 `_validate_skill_name` 铁律),合规。
4. SkillsMiddleware 装配位置:`create_deep_agent` 源码中 `skills` 非空时插在 TodoListMiddleware 之后、
   FilesystemMiddleware 之前(base stack),`modify_request` 用 `append_to_system_message` 注入。
5. **前端硬契约**:`web/src/lib/xhs-blocks.ts` 用正则匹配 ```xhs_topics```/```xhs_copy``` fence 渲染
   卡片;`content_rubric.py` 也靠这两个 fence 判断是否激活评分。→ 这两个 JSON 协议是**系统级机器
   契约**,agent 每轮都必须遵守,不能依赖"agent 恰好读了 skill"。

## 设计决策(已与用户确认)

- **彻底瘦身到单一数据源**:工作流细节只留在 SKILL.md;MAIN_SYSTEM_PROMPT 删掉重复的两步式工作流步骤。
- **但 xhs_topics/xhs_copy 的 JSON 协议契约必须留在 MAIN_SYSTEM_PROMPT**(前端+rubric 硬依赖,
  渐进式披露下 agent 可能不读 skill,协议不能赌)。这是"单一数据源"的正确切分:
  - **机器契约**(输出格式 schema)→ 常驻 prompt
  - **工作流 know-how**(怎么检索、怎么拆解、质量自检清单)→ skill

## 实施步骤

### 1. agent.py:接上官方 skills=
- `create_deep_agent(...)` 增加 `skills=["/skills/"]` 参数。
- 移除手动注释里关于 /skills/ 的说明(由 SkillsMiddleware 接管)。
- baokuan-analyst 子 agent **不接 skills**(纯分析,无需技能库;subagents.py 不动)。

### 2. backends.py:保留 /skills/ route 不变
- SkillsMiddleware 复用主 backend,经 `/skills/` route 读 `.agents/skills/`。已实测可行,零改动。
- (确认:`/skills/` route 仍需要,因为 SkillsMiddleware 通过它 ls/download;不是删 route。)

### 3. prompts.py:MAIN_SYSTEM_PROMPT 瘦身
保留:
- 角色定位(小红书文案创作专家)
- 工具边界硬约束(只用暴露工具、不直连 DB/CLI、不联网)
- **xhs_topics / xhs_copy 的完整 JSON 协议契约**(字段定义、evidence 字段铁律、合法 JSON 单独成段)
- 不编造、有依据、输出中文等硬原则
- 一句指引:涉及"出选题/写文案/按方向创作"时,遵循 topic-content skill 的工作流

删除(移交给 topic-content/SKILL.md 作唯一源):
- 检索优先规则的逐条步骤(skill 里已有)
- 两步式工作流的详细步骤(出选题→等待→写文案→打磨)
- 效果反馈/风格沉淀的操作细节(skill 里已有)

### 4. topic-content/SKILL.md:补齐成唯一工作流源
- 当前 skill 已含完整工作流,核对它是否覆盖 prompt 删掉的全部内容(检索顺序、save_* 调用时机、
  效果反馈、风格沉淀、质量自检)。缺则补齐,确保删 prompt 后无信息丢失。

### 5. 测试
- `tests/test_agent_assembly.py`:新增断言——装配后图中存在 SkillsMiddleware 节点
  (`SkillsMiddleware.before_agent` 出现在 graph nodes),证明 skills 已接线。
- 可能需要的夹具:assembly 测试已 mock env,确认 skills=["/skills/"] 不会在 import 期触发网络
  (SkillsMiddleware 的 ls/download 在 before_agent 运行期才发生,import 期安全)。
- 现有 test_subagents / test_backends 不受影响(backend route 不变)。

### 6. 部署验证(服务器真实环境,本地不跑测试)
- commit + push → 服务器 git pull → langgraph build + compose up -d langgraph → 重启。
- 容器内只读验证:
  - `agent.get_graph().nodes` 含 `SkillsMiddleware.*` 节点。
  - 构造一个 ToolRuntime 跑 SkillsMiddleware.before_agent,确认 skills_metadata 解析出 4 个 skill
    (name/description/path 正确)。
  - 模拟 modify_request,确认 system prompt 注入了 4 个 skill 的清单。
- /ok 200、web 200 冒烟。
- 端到端:真实触发一次对话,看 trace 里 agent 是否按 skill 工作流走(可选,人工浏览器验证)。

## 风险与对策

- **风险:agent 不读 skill 就不按工作流走**。对策:① xhs_topics/xhs_copy 机器契约留 prompt 兜底;
  ② prompt 留一句明确指引"按 topic-content skill 工作流"。渐进式披露本就是官方设计,description
  写得够清楚(已含触发条件)模型就会读。
- **风险:prompt 瘦身后丢信息**。对策:步骤 4 逐条核对 skill 覆盖 prompt 删除项,无遗漏才删。
- **风险:lark skills(lark-base/im/shared)是否该让主 agent 用**。当前主 agent 有
  load_lark_mcp_tools()+feishu_action_tools,这些 skill 描述的正是飞书操作。接上 skills=["/skills/"]
  后它们会一并进 skill 清单——这是**正确的**,主 agent 本就有飞书工具,有了 skill 引导反而更会用。
  不单独排除。

## 不做的事

- 不改 CompositeBackend 路由结构(/skills/ route 保留)。
- 不动 baokuan-analyst 子 agent 的 skills(它不需要)。
- 不把 xhs_topics/xhs_copy 协议挪进 skill(前端硬契约,必须常驻 prompt)。
- 不引入 response_format= 官方结构化输出(与"一轮内既出卡片又对话"不兼容,现有文本协议是合理选择)。
