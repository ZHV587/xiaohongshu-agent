# dbskill 完整融合实施计划

> **给执行型智能体的要求：** 实施本计划时，必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐任务执行。步骤使用 checkbox（`- [ ]`）语法跟踪进度。

**目标：** 将 `dontbesilent2025/dbskill` 完整融合进小红书智能体，做到上游能力可对齐、本地 `xhs-*` 能力可落地、知识原子可导入、路由别名可兼容，并用测试防止后续漂移。

**架构：** 把上游 `dbskill` 当作方法论源头，把本项目当作小红书场景下的产品化运行时。融合通过覆盖清单、本地 `.agents/skills/` 技能文件、`prompts.py` 路由别名、`scripts/migrate_atoms.py` 知识原子导入，以及 contract tests 共同完成。每个上游能力都必须被标记为：已实现、已折叠、缺失待补，或明确排除并说明原因。

**技术栈：** Python、pytest、DeepAgents 官方 `skills=["/skills/"]`、本地 Markdown `SKILL.md`、Postgres 数据底座、可选飞书同步、Windows PowerShell。

---

## 文件结构

- 新建 `docs/dbskill-integration-matrix.md`：给人看的融合矩阵，说明上游 `/dbs-*` 命令如何映射到本地 `xhs-*` skill。
- 新建 `dbskill_manifest.py`：给测试和维护脚本使用的机器可读能力清单。
- 新建 `tests/test_dbskill_integration_contract.py`：验证 skill 文件、触发别名和融合清单覆盖率。
- 修改 `prompts.py`：补齐 `/dbs-*` 别名，并路由到正确的本地能力。
- 修改相关 `.agents/skills/*/SKILL.md`：补上缺失的 `/dbs-*` 触发别名，并说明哪些上游能力被折叠进本地技能。
- 仅在“折叠会掩盖关键行为”的情况下新建 skill：
  - `.agents/skills/xhs-slowisfast/SKILL.md`
  - `.agents/skills/xhs-good-question/SKILL.md`
  - `.agents/skills/xhs-goal/SKILL.md`
  - `.agents/skills/xhs-deconstruct/SKILL.md`
  - `.agents/skills/xhs-chatroom-austrian/SKILL.md`
  - `.agents/skills/xhs-dbskill-upgrade/SKILL.md`
- 修改 `scripts/migrate_atoms.py`：增加 status/audit 模式，用于验证知识原子覆盖情况，不写入数据库。
- 新建 `tests/test_dbskill_atoms_contract.py`：验证迁移脚本保留 `resource_type="dbskill_atom"`，并提供 dry-run/status 路径。

---

### 任务 1：增加机器可读的 dbskill 融合清单

**文件：**
- 新建：`dbskill_manifest.py`
- 测试：`tests/test_dbskill_integration_contract.py`

- [ ] **步骤 1：先写失败测试**

```python
# tests/test_dbskill_integration_contract.py
from dbskill_manifest import DBSKILL_UPSTREAM_VERSION, DBSKILL_CAPABILITIES


def test_dbskill_manifest_tracks_current_upstream_version():
    assert DBSKILL_UPSTREAM_VERSION == "v2.14.2"


def test_every_manifest_entry_has_local_integration_status():
    assert len(DBSKILL_CAPABILITIES) >= 21
    for item in DBSKILL_CAPABILITIES:
        assert item["upstream_command"].startswith("/dbs")
        assert item["local_status"] in {"implemented", "folded", "missing", "excluded"}
        assert item["local_target"]
        assert item["reason"]
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：失败，报 `ModuleNotFoundError: No module named 'dbskill_manifest'`。

- [ ] **步骤 3：创建融合清单**

```python
# dbskill_manifest.py
"""dbskill upstream-to-local integration manifest."""

DBSKILL_UPSTREAM_REPO = "https://github.com/dontbesilent2025/dbskill"
DBSKILL_UPSTREAM_VERSION = "v2.14.2"

DBSKILL_CAPABILITIES = [
    {"upstream_command": "/dbs", "local_target": "prompts.py:xhs-router", "local_status": "implemented", "reason": "主路由已产品化为小红书智能体的 xhs-router。"},
    {"upstream_command": "/dbs-diagnosis", "local_target": ".agents/skills/xhs-diagnosis/SKILL.md", "local_status": "implemented", "reason": "商业诊断已实现为 xhs-diagnosis。"},
    {"upstream_command": "/dbs-benchmark", "local_target": ".agents/skills/xhs-benchmark/SKILL.md", "local_status": "implemented", "reason": "对标研究已实现为 xhs-benchmark。"},
    {"upstream_command": "/dbs-content", "local_target": ".agents/skills/xhs-content/SKILL.md", "local_status": "implemented", "reason": "内容诊断已实现为 xhs-content。"},
    {"upstream_command": "/dbs-content-system", "local_target": ".agents/skills/xhs-content-system/SKILL.md", "local_status": "implemented", "reason": "内容系统已实现为小红书云原生内容结构化流程。"},
    {"upstream_command": "/dbs-hook", "local_target": ".agents/skills/xhs-hook/SKILL.md", "local_status": "implemented", "reason": "开头钩子优化已实现为 xhs-hook。"},
    {"upstream_command": "/dbs-xhs-title", "local_target": ".agents/skills/xhs-title/SKILL.md", "local_status": "implemented", "reason": "标题公式已实现为 xhs-title。"},
    {"upstream_command": "/dbs-ai-check", "local_target": ".agents/skills/xhs-audit/SKILL.md", "local_status": "implemented", "reason": "AI 味检测和文案审计已实现为 xhs-audit。"},
    {"upstream_command": "/dbs-action", "local_target": ".agents/skills/xhs-action/SKILL.md", "local_status": "implemented", "reason": "执行力与工作流诊断已实现为 xhs-action。"},
    {"upstream_command": "/dbs-good-question", "local_target": ".agents/skills/xhs-good-question/SKILL.md", "local_status": "missing", "reason": "目前折叠在 xhs-action 中；完整融合应暴露为独立 skill。"},
    {"upstream_command": "/dbs-slowisfast", "local_target": ".agents/skills/xhs-slowisfast/SKILL.md", "local_status": "missing", "reason": "目前部分覆盖在工作流审计中；完整融合应暴露为独立 skill。"},
    {"upstream_command": "/dbs-deconstruct", "local_target": ".agents/skills/xhs-deconstruct/SKILL.md", "local_status": "missing", "reason": "目前折叠在定位与路由提示中；应成为显式的概念拆解 skill。"},
    {"upstream_command": "/dbs-goal", "local_target": ".agents/skills/xhs-goal/SKILL.md", "local_status": "missing", "reason": "目标审计目前只存在于路由文案中；应独立实现。"},
    {"upstream_command": "/dbs-decision", "local_target": ".agents/skills/xhs-decision/SKILL.md", "local_status": "implemented", "reason": "决策系统已实现为 xhs-decision。"},
    {"upstream_command": "/dbs-learning", "local_target": ".agents/skills/xhs-learning/SKILL.md", "local_status": "implemented", "reason": "自适应学习已实现为 xhs-learning。"},
    {"upstream_command": "/dbs-save", "local_target": ".agents/skills/xhs-system/SKILL.md", "local_status": "implemented", "reason": "存档流程已实现为 xhs-system。"},
    {"upstream_command": "/dbs-restore", "local_target": ".agents/skills/xhs-system/SKILL.md", "local_status": "implemented", "reason": "恢复流程已实现为 xhs-system。"},
    {"upstream_command": "/dbs-report", "local_target": ".agents/skills/xhs-system/SKILL.md", "local_status": "folded", "reason": "路由已提到 report；xhs-system 需要补充报告打包路径。"},
    {"upstream_command": "/dbs-agent-migration", "local_target": ".agents/skills/xhs-system/SKILL.md", "local_status": "folded", "reason": "工作台迁移审计已由 xhs-system 覆盖。"},
    {"upstream_command": "/dbs-chatroom", "local_target": ".agents/skills/xhs-chatroom/SKILL.md", "local_status": "implemented", "reason": "多专家讨论已实现为 xhs-chatroom。"},
    {"upstream_command": "/dbs-chatroom-austrian", "local_target": ".agents/skills/xhs-chatroom-austrian/SKILL.md", "local_status": "missing", "reason": "已有通用聊天室，但奥派模式还不是显式能力。"},
    {"upstream_command": "/dbskill-upgrade", "local_target": ".agents/skills/xhs-dbskill-upgrade/SKILL.md", "local_status": "missing", "reason": "目前没有本地上游版本审计或升级工作流。"},
]
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add dbskill_manifest.py tests/test_dbskill_integration_contract.py
git commit -m "test: add dbskill integration manifest contract"
```

---

### 任务 2：生成给人看的融合矩阵

**文件：**
- 新建：`docs/dbskill-integration-matrix.md`
- 修改：`tests/test_dbskill_integration_contract.py`

- [ ] **步骤 1：增加失败的文档覆盖测试**

```python
# tests/test_dbskill_integration_contract.py
from pathlib import Path
from dbskill_manifest import DBSKILL_CAPABILITIES


def test_dbskill_integration_matrix_mentions_every_upstream_command():
    text = Path("docs/dbskill-integration-matrix.md").read_text(encoding="utf-8")
    for item in DBSKILL_CAPABILITIES:
        assert item["upstream_command"] in text
        assert item["local_target"] in text
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_integration_contract.py::test_dbskill_integration_matrix_mentions_every_upstream_command -q`

预期：失败，报 `FileNotFoundError`。

- [ ] **步骤 3：创建融合矩阵文档**

```markdown
# dbskill 融合矩阵

上游仓库：https://github.com/dontbesilent2025/dbskill
跟踪版本：v2.14.2

| 上游命令 | 本地目标 | 状态 | 说明 |
| --- | --- | --- | --- |
| /dbs | prompts.py:xhs-router | 已实现 | 主路由已产品化为 xhs-router。 |
| /dbs-diagnosis | .agents/skills/xhs-diagnosis/SKILL.md | 已实现 | 商业诊断。 |
| /dbs-benchmark | .agents/skills/xhs-benchmark/SKILL.md | 已实现 | 对标研究。 |
| /dbs-content | .agents/skills/xhs-content/SKILL.md | 已实现 | 内容诊断。 |
| /dbs-content-system | .agents/skills/xhs-content-system/SKILL.md | 已实现 | 云原生内容系统。 |
| /dbs-hook | .agents/skills/xhs-hook/SKILL.md | 已实现 | 开头钩子优化。 |
| /dbs-xhs-title | .agents/skills/xhs-title/SKILL.md | 已实现 | 标题公式。 |
| /dbs-ai-check | .agents/skills/xhs-audit/SKILL.md | 已实现 | AI 味与文案审计。 |
| /dbs-action | .agents/skills/xhs-action/SKILL.md | 已实现 | 执行力诊断。 |
| /dbs-good-question | .agents/skills/xhs-good-question/SKILL.md | 缺失 | 新增独立 skill。 |
| /dbs-slowisfast | .agents/skills/xhs-slowisfast/SKILL.md | 缺失 | 新增独立 skill。 |
| /dbs-deconstruct | .agents/skills/xhs-deconstruct/SKILL.md | 缺失 | 新增独立 skill。 |
| /dbs-goal | .agents/skills/xhs-goal/SKILL.md | 缺失 | 新增独立 skill。 |
| /dbs-decision | .agents/skills/xhs-decision/SKILL.md | 已实现 | 决策系统。 |
| /dbs-learning | .agents/skills/xhs-learning/SKILL.md | 已实现 | 自适应学习。 |
| /dbs-save | .agents/skills/xhs-system/SKILL.md | 已实现 | 会话存档。 |
| /dbs-restore | .agents/skills/xhs-system/SKILL.md | 已实现 | 会话恢复。 |
| /dbs-report | .agents/skills/xhs-system/SKILL.md | 已折叠 | 补充报告打包说明。 |
| /dbs-agent-migration | .agents/skills/xhs-system/SKILL.md | 已折叠 | 工作台迁移审计。 |
| /dbs-chatroom | .agents/skills/xhs-chatroom/SKILL.md | 已实现 | 多专家讨论。 |
| /dbs-chatroom-austrian | .agents/skills/xhs-chatroom-austrian/SKILL.md | 缺失 | 新增奥派聊天室模式。 |
| /dbskill-upgrade | .agents/skills/xhs-dbskill-upgrade/SKILL.md | 缺失 | 新增版本审计工作流。 |
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add docs/dbskill-integration-matrix.md tests/test_dbskill_integration_contract.py
git commit -m "docs: document dbskill integration matrix"
```

---

### 任务 3：确认本地 skill 文件存在，或被明确折叠

**文件：**
- 修改：`tests/test_dbskill_integration_contract.py`

- [ ] **步骤 1：写失败的 contract test**

```python
# tests/test_dbskill_integration_contract.py
from pathlib import Path
from dbskill_manifest import DBSKILL_CAPABILITIES


def test_implemented_and_missing_dbskill_targets_have_skill_files():
    for item in DBSKILL_CAPABILITIES:
        target = item["local_target"]
        if target.startswith(".agents/skills/"):
            assert Path(target).exists(), f"Missing local skill target for {item['upstream_command']}: {target}"
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_integration_contract.py::test_implemented_and_missing_dbskill_targets_have_skill_files -q`

预期：失败，并列出缺失的独立 skill 文件。

- [ ] **步骤 3：新增缺失的独立 skill**

每个缺失的 `SKILL.md` 至少要有合法 frontmatter，例如：

```markdown
---
name: xhs-good-question
description: 好问题说明书。把模糊请求改写成可执行、可验证、可交付的问题。触发方式：/xhs-good-question、/dbs-good-question、「好问题」「问题说清楚」「提问说明书」
---

# xhs-good-question：好问题说明书

使用本 skill 时，先识别用户当前问题的模糊点，再输出一个可执行的问题说明书。
```

用等价结构补齐：

```text
.agents/skills/xhs-slowisfast/SKILL.md
.agents/skills/xhs-goal/SKILL.md
.agents/skills/xhs-deconstruct/SKILL.md
.agents/skills/xhs-chatroom-austrian/SKILL.md
.agents/skills/xhs-dbskill-upgrade/SKILL.md
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills/xhs-good-question .agents/skills/xhs-slowisfast .agents/skills/xhs-goal .agents/skills/xhs-deconstruct .agents/skills/xhs-chatroom-austrian .agents/skills/xhs-dbskill-upgrade tests/test_dbskill_integration_contract.py
git commit -m "feat: add missing dbskill-derived xhs skills"
```

---

### 任务 4：让 `/dbs-*` 成为 skill frontmatter 的一等别名

**文件：**
- 修改：`dbskill_manifest.py` 中映射到的所有 `.agents/skills/xhs-*/SKILL.md`
- 修改：`tests/test_dbskill_integration_contract.py`

- [ ] **步骤 1：写失败的 alias 测试**

```python
# tests/test_dbskill_integration_contract.py
from pathlib import Path
from dbskill_manifest import DBSKILL_CAPABILITIES


def test_each_skill_mentions_its_upstream_dbs_alias():
    for item in DBSKILL_CAPABILITIES:
        target = item["local_target"]
        if target.startswith(".agents/skills/"):
            text = Path(target).read_text(encoding="utf-8")
            assert item["upstream_command"] in text, f"{target} does not mention {item['upstream_command']}"
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_integration_contract.py::test_each_skill_mentions_its_upstream_dbs_alias -q`

预期：失败，列出只写了 `/xhs-*`、没有写 `/dbs-*` 的技能。

- [ ] **步骤 3：更新 skill 描述**

给每个已映射 skill 的 `description` 触发方式补上对应上游别名。示例：

```markdown
description: 小红书标题公式工具。触发方式：/xhs-title、/dbs-xhs-title、/小红书标题、「帮我起个标题」「标题公式」「标题怎么写」
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills tests/test_dbskill_integration_contract.py
git commit -m "feat: expose dbskill aliases in local skills"
```

---

### 任务 5：补齐主路由别名覆盖

**文件：**
- 修改：`prompts.py`
- 修改：`tests/test_dbskill_integration_contract.py`

- [ ] **步骤 1：写失败的路由测试**

```python
# tests/test_dbskill_integration_contract.py
from pathlib import Path
from dbskill_manifest import DBSKILL_CAPABILITIES


def test_router_mentions_every_upstream_dbs_command():
    prompt = Path("prompts.py").read_text(encoding="utf-8")
    for item in DBSKILL_CAPABILITIES:
        assert item["upstream_command"] in prompt, f"Router missing {item['upstream_command']}"
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_integration_contract.py::test_router_mentions_every_upstream_dbs_command -q`

预期：失败，列出 `prompts.py` 尚未包含的别名。

- [ ] **步骤 3：给路由文案补上缺失别名**

更新 `MAIN_SYSTEM_PROMPT` 的路由段落，让每个上游别名至少出现一次，并指向产品化后的本地能力。保留 `xhs_topics`、`xhs_copy` 等机器输出契约在主 prompt 中。

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`uv run pytest tests/test_dbskill_integration_contract.py -q`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add prompts.py tests/test_dbskill_integration_contract.py
git commit -m "feat: complete dbskill router aliases"
```

---

### 任务 6：验证知识原子库融合

**文件：**
- 修改：`scripts/migrate_atoms.py`
- 新建：`tests/test_dbskill_atoms_contract.py`

- [ ] **步骤 1：写失败的脚本契约测试**

```python
# tests/test_dbskill_atoms_contract.py
import scripts.migrate_atoms as migrate_atoms


def test_dbskill_atoms_use_stable_resource_type():
    assert migrate_atoms.RESOURCE_TYPE == "dbskill_atom"


def test_dbskill_atoms_script_exposes_status_mode():
    assert hasattr(migrate_atoms, "check_import_status")
```

- [ ] **步骤 2：运行测试，确认它按预期失败**

运行：`uv run pytest tests/test_dbskill_atoms_contract.py -q`

预期：失败，提示缺少 `check_import_status`。

- [ ] **步骤 3：增加 status 函数**

```python
# scripts/migrate_atoms.py
def check_import_status() -> dict[str, object]:
    atoms = load_atoms()
    return {
        "resource_type": RESOURCE_TYPE,
        "source_count": len(atoms),
        "source_url": ATOMS_URL,
    }
```

在脚本入口中增加 `--status` 处理，打印返回字典，不写入 Postgres 或飞书。

- [ ] **步骤 4：运行测试和 dry status**

运行：`uv run pytest tests/test_dbskill_atoms_contract.py -q`

预期：通过。

运行：`uv run python scripts/migrate_atoms.py --status`

预期：打印 `resource_type`、`source_count`、`source_url`，不导入记录。

- [ ] **步骤 5：提交**

```bash
git add scripts/migrate_atoms.py tests/test_dbskill_atoms_contract.py
git commit -m "feat: add dbskill atom import status audit"
```

---

### 任务 7：完整回归验证

**文件：**
- 除非测试暴露真实缺陷，否则不改代码。

- [ ] **步骤 1：运行 Python 测试**

运行：`uv run pytest -q`

预期：全部通过。

- [ ] **步骤 2：运行前端单元测试**

在 `web/` 目录运行：`npm run test:unit`

预期：全部通过。

- [ ] **步骤 3：运行 TypeScript 和 ESLint**

在 `web/` 目录运行：`.\node_modules\.bin\tsc.CMD --noEmit`

预期：无错误。

在 `web/` 目录运行：`.\node_modules\.bin\eslint.CMD src`

预期：无错误。

- [ ] **步骤 4：运行构建检查**

运行：`uv build`

预期：源码包和 wheel 构建成功。

在 `web/` 目录运行：`npm run build`

预期：Next.js 构建成功。

- [ ] **步骤 5：提交**

```bash
git status --short
git commit -m "chore: verify full dbskill integration"
```

---

## 自检

**需求覆盖：** 本计划覆盖上游版本跟踪、命令覆盖、本地 skill 文件、路由别名、文档、知识原子导入状态和回归检查。

**占位扫描：** 计划包含具体路径、命令、测试和实现示例。缺失 skill 的正文需要领域写作，但每个缺失目标和最低 frontmatter 要求都已明确列出。

**类型一致性：** 清单在测试和文档中统一使用 `upstream_command`、`local_target`、`local_status`、`reason`。
