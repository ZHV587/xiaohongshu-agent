# Sub-agent 架构分层重构验收计划

**日期**：2026-07-03
**状态**：已实施并通过本地验收
**目标**：按 DeepAgents 官方 `create_deep_agent(subagents=[...])` / `SubAgent` 扩展方式接入对标分析与专家辩论能力，删除过度 Skill 壳层，避免自研私有子代理机制。

## 1. 范围

- 保留执行型子代理：`knowledge-atom-retriever`、`persona-distiller`。
- 新增官方 SubAgent：`benchmark-analyst`、`expert-panel-debater`。
- 删除冗余 Skill：`xhs-benchmark`、`xhs-chatroom`、`xhs-dbskill-upgrade`。
- `xhs-system` 继续作为主控直调工具路径，不做子代理套壳。
- `xhs-content-system` 保持内容工程化 Skill，不再承担对标分析入口。

## 2. 官方扩展约束

- 子代理定义必须只使用 `deepagents.middleware.subagents.SubAgent` 的公开字段。
- 子代理注册必须通过 `build_executor_subagents(...)` 返回给 `create_deep_agent(subagents=...)`。
- 子代理输出结构使用官方支持的 `response_format` 字段承载 Pydantic 契约。
- 模型热加载继续使用公开 middleware 字段挂载 `build_router_middleware(registry)`。
- 不接入 DeepAgents 私有 tracing hook；观测按官方 `lc_agent_name` metadata 过滤。

## 3. 实施清单

- [x] `subagents_executor.py` 引入公开 `SubAgent` 类型并返回 `list[SubAgent]`。
- [x] 新增 `BenchmarkReport`、`ExpertPanelOpinion`、`DebateVerdictReport` 输出契约。
- [x] 新增 `benchmark-analyst`，用于隔离检索和精读对标爆款素材。
- [x] 新增 `expert-panel-debater`，用于隔离多角色诊断和共识输出。
- [x] `prompts.py` 将找同行、拆爆款、真对标路由到 `task -> benchmark-analyst`。
- [x] `prompts.py` 将多角色讨论、奥派经济视角路由到 `task -> expert-panel-debater`。
- [x] 删除 `xhs-benchmark`、`xhs-chatroom`、`xhs-dbskill-upgrade` Skill 文件。
- [x] 更新所有剩余 Skill 的交叉引用，避免继续指向已删除 Skill。
- [x] 更新 `scripts/migrate_atoms.py`，将旧 `dbs-benchmark` 原子映射到 `benchmark-analyst`。
- [x] 新增 `scripts/dbskill_audit.py`，防止被删除 Skill 回流。
- [x] 修复 `scripts/runtime_import_smoke.py` 的 repo root 导入路径，保证部署烟测可直接运行。

## 4. 验收结果

- `uv run pytest tests/test_subagents_refactoring.py -q`：通过。
- `uv run pytest tests/test_subagents.py tests/test_agent_assembly.py::test_agent_registers_executor_subagents tests/test_agent_assembly.py::test_knowledge_retriever_subagent_has_evidence_response_format tests/test_agent_assembly.py::test_knowledge_retriever_subagent_uses_data_foundation_retrieval_tools -q`：通过。
- `uv run pytest tests/test_migrate_atoms.py::test_map_atom_skills_uses_local_xhs_skill_names tests/test_dbskill_alias_coverage.py::test_skill_body_cross_refs_point_to_real_skills tests/test_storage_policy.py tests/test_user_visible_skill_language.py -q`：通过。
- `uv run python scripts/runtime_import_smoke.py`：通过。
- `uv run python scripts/dbskill_audit.py`：通过。
- `uv run pytest -q`：589 passed, 125 skipped。

## 5. 生产部署确认

- [x] 本地全量测试通过。
- [x] 子代理定义未使用私有字段。
- [x] 文档未要求私有 tracing hook。
- [x] 旧 Skill 文件已删除。
- [x] 推送到远端仓库。
- [x] 部署到生产服务器。
- [x] 生产健康检查通过：`module.scheduler=healthy`、`module.database=healthy`、`public_http_status=200`。
- [x] 生产浏览器 UAT 通过：桌面端登录态页面可打开，Enter 可发送消息，对话响应落地，无 console error、page error、request failure 或 4xx/5xx。
