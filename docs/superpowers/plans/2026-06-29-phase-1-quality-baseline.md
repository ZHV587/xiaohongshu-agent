# Phase 1 Quality Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 1 of the hardening design real: Python tests are insulated from host proxy variables, and user-visible product surfaces no longer expose internal skill names or workflow slugs.

**Architecture:** Keep production runtime behavior unchanged. Add test-only proxy cleanup in the shared pytest setup, update frontend tool rendering to use generic skill activation labels, and clean only user-facing skill snippets while preserving internal execution instructions and routing metadata.

**Tech Stack:** Python 3.12, pytest, LangChain/LangGraph model construction tests, Next.js/TypeScript, Node test runner, Markdown skill files.

---

## Scope

This plan implements only Phase 1 from `docs/superpowers/specs/2026-06-29-quality-architecture-operations-design.md`.

Do not implement Phase 2 frontend hook extraction or Phase 3 production smoke/operations work in this plan.

## File Map

- Modify `tests/conftest.py`: central test-only cleanup for host proxy environment variables.
- Create `tests/test_test_environment.py`: regression tests for proxy cleanup helpers.
- Modify `tests/test_models.py`: remove local `NO_PROXY` special case and rely on shared cleanup.
- Modify `web/tests/tool-render.test.ts`: change tests so skill activation labels must be generic and must not expose slugs.
- Modify `web/src/lib/tool-render.tsx`: return generic skill activation wording from `resolveToolRender`.
- Create `tests/test_user_visible_skill_language.py`: scan targeted user-facing snippets in selected skills.
- Modify selected skill files:
  - `.agents/skills/topic-content/SKILL.md`
  - `.agents/skills/xhs-copywriting/SKILL.md`
  - `.agents/skills/xhs-content-system/SKILL.md`
  - `.agents/skills/xhs-benchmark/SKILL.md`
  - `.agents/skills/xhs-content/SKILL.md`
  - `.agents/skills/xhs-action/SKILL.md`

---

### Task 1: Centralize Pytest Proxy Cleanup

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/test_test_environment.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing proxy cleanup tests**

Create `tests/test_test_environment.py`:

```python
import os

from tests.conftest import HOST_PROXY_ENV_VARS, clear_host_proxy_env, normalize_no_proxy


def test_clear_host_proxy_env_removes_upper_and_lowercase_proxy_vars(monkeypatch):
    for key in HOST_PROXY_ENV_VARS:
        monkeypatch.setenv(key, "socks5://127.0.0.1:7897")

    removed = clear_host_proxy_env()

    assert removed == sorted(HOST_PROXY_ENV_VARS)
    for key in HOST_PROXY_ENV_VARS:
        assert key not in os.environ


def test_normalize_no_proxy_removes_ipv6_entries_but_keeps_hostnames(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,example.com")

    normalize_no_proxy()

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,example.com"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_test_environment.py -q
```

Expected: FAIL because `HOST_PROXY_ENV_VARS`, `clear_host_proxy_env`, and `normalize_no_proxy` do not exist yet.

- [ ] **Step 3: Implement shared cleanup helpers**

Replace `tests/conftest.py` with:

```python
import os

import pytest


HOST_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def clear_host_proxy_env() -> list[str]:
    """Remove host proxy variables so offline model tests stay machine-independent."""
    removed: list[str] = []
    for key in HOST_PROXY_ENV_VARS:
        if key in os.environ:
            os.environ.pop(key, None)
            removed.append(key)
    return sorted(removed)


def normalize_no_proxy() -> None:
    """Fix httpx NO_PROXY parsing on Windows when IPv6 entries such as ::1 are present."""
    if "NO_PROXY" not in os.environ:
        return
    os.environ["NO_PROXY"] = ",".join(
        item for item in os.environ["NO_PROXY"].split(",")
        if ":" not in item
    )


def pytest_configure(config):
    normalize_no_proxy()
    clear_host_proxy_env()


@pytest.fixture(autouse=True)
def _isolate_host_proxy_env(monkeypatch):
    for key in HOST_PROXY_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
```

- [ ] **Step 4: Remove the now-redundant local proxy cleanup from model tests**

In `tests/test_models.py`, update `test_build_chat_model_providers` by deleting these lines:

```python
    # Ensure NO_PROXY does not cause httpx initialization failures
    monkeypatch.delenv("NO_PROXY", raising=False)

```

The test should start like this after the change:

```python
def test_build_chat_model_providers(monkeypatch):
    from models import _build_chat_model
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI

    # Test anthropic
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
```

- [ ] **Step 5: Run focused Python tests**

Run:

```powershell
uv run pytest tests/test_test_environment.py tests/test_models.py::test_build_chat_model_providers -q
```

Expected: PASS.

- [ ] **Step 6: Run the previously failing assembly area with a host proxy set**

Run:

```powershell
$env:HTTPS_PROXY='socks5://127.0.0.1:7897'
uv run pytest tests/test_agent_assembly.py tests/test_models.py::test_build_chat_model_providers -q
```

Expected: PASS. The autouse fixture and configure hook isolate test execution from the host proxy.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add -- tests/conftest.py tests/test_test_environment.py tests/test_models.py
git commit -m "test: isolate pytest from host proxy env"
```

---

### Task 2: Hide Skill Slugs in Frontend Thinking Labels

**Files:**
- Modify: `web/tests/tool-render.test.ts`
- Modify: `web/src/lib/tool-render.tsx`

- [ ] **Step 1: Update frontend tests to require generic skill labels**

In `web/tests/tool-render.test.ts`, replace the first two tests with:

```ts
test("读取 SKILL.md 渲染为通用方法整理步骤,不暴露具体技能名", () => {
  const spec = resolveToolRender("read_file", {
    file_path: "/skills/xhs-copywriting/SKILL.md",
  });
  assert.notEqual(spec.aura, "hidden");
  if (spec.aura === "hidden") throw new Error("unreachable");
  assert.equal(spec.aura.running, "正在整理方法…");
  assert.equal(spec.aura.done({ name: "read_file" }), "已整理好方法");
  assert.doesNotMatch(spec.aura.running, /xhs-|copywriting|技能|skill/i);
});

test("非 xhs 前缀的 skill 也使用同一通用文案", () => {
  const spec = resolveToolRender("read_file", {
    file_path: "/skills/topic-content/SKILL.md",
  });
  assert.notEqual(spec.aura, "hidden");
  if (spec.aura === "hidden") throw new Error("unreachable");
  assert.equal(spec.aura.running, "正在整理方法…");
  assert.equal(spec.aura.done({ name: "read_file" }), "已整理好方法");
  assert.doesNotMatch(spec.aura.running, /topic-content|技能|skill/i);
});
```

- [ ] **Step 2: Run the focused frontend test to verify it fails**

Run:

```powershell
cd web
node --import tsx --test tests/tool-render.test.ts
```

Expected: FAIL because `resolveToolRender` still returns labels containing the skill slug.

- [ ] **Step 3: Implement generic skill activation labels**

In `web/src/lib/tool-render.tsx`, replace this block:

```ts
  const skillMatch = path.match(/\/skills\/([^/]+)\/SKILL\.md$/i);
  if (skillMatch) {
    const slug = skillMatch[1].replace(/^xhs-/, "");
    return {
      aura: {
        running: `正在调取「${slug}」技能…`,
        done: () => `已运用「${slug}」技能`,
      },
    };
  }
```

with:

```ts
  const skillMatch = path.match(/\/skills\/[^/]+\/SKILL\.md$/i);
  if (skillMatch) {
    return {
      aura: {
        running: "正在整理方法…",
        done: () => "已整理好方法",
      },
    };
  }
```

Also update the nearby comment from:

```ts
  // skill 激活是"通用思考链"的信号:读取某 skill 的 SKILL.md = 智能体正在运用该技能。
```

to:

```ts
  // 读取方法文件是思考链信号，但用户不需要看到内部名称。
```

- [ ] **Step 4: Run focused frontend tests**

Run:

```powershell
cd web
node --import tsx --test tests/tool-render.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add -- web/src/lib/tool-render.tsx web/tests/tool-render.test.ts
git commit -m "fix(ui): hide skill slugs in thinking labels"
```

---

### Task 3: Add Skill User-Facing Language Contract

**Files:**
- Create: `tests/test_user_visible_skill_language.py`
- Modify: selected `.agents/skills/*/SKILL.md` files in Task 4

- [ ] **Step 1: Write the failing wording contract test**

Create `tests/test_user_visible_skill_language.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

USER_VISIBLE_MARKERS = (
    "直接告诉用户",
    "输出以下引导词",
    "| 对标找到了",
    "| 诊断出开头问题",
    "| 诊断出标题问题",
    "| 诊断出明显 AI 味",
    "| 用户在方法上走捷径",
    "| 内容涉及对标和平台选择",
    "| 选题装配完成",
    "| 主题地图完成",
    "| 文案写完需要质检",
    "| 执行力诊断后",
    "| 问题说明书完成",
)

FORBIDDEN_USER_VISIBLE_TOKENS = (
    "`xhs-",
    "转入 `xhs-",
    "使用专门的 `xhs-",
    "技能来",
    "system prompt",
    "主控 §",
    "主控 system prompt",
)

TARGET_SKILLS = (
    "topic-content",
    "xhs-copywriting",
    "xhs-content-system",
    "xhs-benchmark",
    "xhs-content",
    "xhs-action",
)


def _skill_text(name: str) -> str:
    return (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _user_visible_lines(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    result: list[tuple[int, str]] = []
    in_guidance_block = False
    for idx, line in enumerate(lines, start=1):
        if "输出以下引导词" in line:
            in_guidance_block = True
            result.append((idx, line))
            continue
        if in_guidance_block:
            result.append((idx, line))
            if line.strip().endswith("```") and idx > 1:
                in_guidance_block = False
            continue
        if any(marker in line for marker in USER_VISIBLE_MARKERS):
            result.append((idx, line))
    return result


def test_user_visible_skill_lines_do_not_expose_internal_names():
    failures: list[str] = []
    for skill in TARGET_SKILLS:
        for line_no, line in _user_visible_lines(_skill_text(skill)):
            for token in FORBIDDEN_USER_VISIBLE_TOKENS:
                if token in line:
                    failures.append(f"{skill}:{line_no}: contains {token!r}: {line}")
    assert failures == []
```

- [ ] **Step 2: Run the wording test to verify it fails**

Run:

```powershell
uv run pytest tests/test_user_visible_skill_language.py -q
```

Expected: FAIL with lines from the targeted skill files that expose `xhs-*`, `技能`, or prompt-section language in user-visible snippets.

- [ ] **Step 3: Commit the failing test only if your workflow requires red commits**

If following strict red/green commits, run:

```powershell
git add -- tests/test_user_visible_skill_language.py
git commit -m "test: guard user visible skill wording"
```

If the team does not want failing commits on `master`, skip this commit and commit the test together with Task 4.

---

### Task 4: Clean User-Facing Skill Snippets

**Files:**
- Modify: `.agents/skills/topic-content/SKILL.md`
- Modify: `.agents/skills/xhs-copywriting/SKILL.md`
- Modify: `.agents/skills/xhs-content-system/SKILL.md`
- Modify: `.agents/skills/xhs-benchmark/SKILL.md`
- Modify: `.agents/skills/xhs-content/SKILL.md`
- Modify: `.agents/skills/xhs-action/SKILL.md`
- Test: `tests/test_user_visible_skill_language.py`

- [ ] **Step 1: Update `topic-content` user guidance**

In `.agents/skills/topic-content/SKILL.md`, replace the guidance block under "场景二:用户要写文案" with:

```markdown
已为您锁定这个选题。

下一步我可以继续帮您写完整正文：先给 3 个标题方向，再给开头方案，最后生成完整笔记。

您可以直接说：**【写完整文案】**。
```

Keep the surrounding internal instruction that this handoff is for writing copy, but do not expose the internal skill name in the quoted user-facing block.

- [ ] **Step 2: Update `xhs-copywriting` next-step table**

In `.agents/skills/xhs-copywriting/SKILL.md`, replace:

```markdown
| 文案写完需要质检 | 「写完了，做个 AI 味检测和润色。」转入 `xhs-audit` |
```

with:

```markdown
| 文案写完需要质检 | 「写完了，做个 AI 味检测和润色。」 |
```

Do not remove internal tool and state instructions elsewhere in the file.

- [ ] **Step 3: Update `xhs-content-system` transition table**

In `.agents/skills/xhs-content-system/SKILL.md`, replace:

```markdown
| 选题装配完成，需要写文案 | 「选题有了，下一步写标题和开头。」转入 `xhs-copywriting` |
| 主题地图完成，想做深入对标 | 「主题地图有了，下一步拆解同类爆款。」转入 `xhs-benchmark` |
```

with:

```markdown
| 选题装配完成，需要写文案 | 「选题有了，下一步我可以继续帮你写标题、开头和正文。」 |
| 主题地图完成，想做深入对标 | 「主题地图有了，下一步可以拆解同类爆款，找出可复用的表达机制。」 |
```

- [ ] **Step 4: Update `xhs-benchmark` transition table**

In `.agents/skills/xhs-benchmark/SKILL.md`, replace:

```markdown
| 对标找到了，需要写具体文案 | 「用公式起标题和开头。」转入 `xhs-copywriting` |
```

with:

```markdown
| 对标找到了，需要写具体文案 | 「对标已经清楚了，下一步可以用这些规律起标题、写开头和正文。」 |
```

- [ ] **Step 5: Update `xhs-content` transition table**

In `.agents/skills/xhs-content/SKILL.md`, replace:

```markdown
| 诊断出开头问题 | 「开头有问题。优化开头，生成10个方案。」转入 `xhs-hook` |
| 诊断出标题问题 | 「标题单独做。」转入 `xhs-title` |
| 诊断出明显 AI 味 | 「AI 味单独过一遍更清楚。」转入 `xhs-audit` |
| 用户在方法上走捷径 | 「你现在不只是差一点内容技巧，是在绕开关键摩擦。」转入 `xhs-action` |
| 内容涉及对标和平台选择 | 「平台怎么做，先找对标模仿。」转入 `xhs-benchmark` |
```

with:

```markdown
| 诊断出开头问题 | 「开头有问题，我可以继续帮你重新设计开头方案。」 |
| 诊断出标题问题 | 「标题需要单独打磨，我可以继续给你换一批更有点击欲的标题。」 |
| 诊断出明显 AI 味 | 「AI 味比较明显，我可以继续帮你做一轮清洗和改写。」 |
| 用户在方法上走捷径 | 「你现在不只是差一点内容技巧，是在绕开关键摩擦。」 |
| 内容涉及对标和平台选择 | 「平台怎么做，先找对标模仿，把可复用规律拆出来。」 |
```

- [ ] **Step 6: Update `xhs-action` user-facing transition lines**

In `.agents/skills/xhs-action/SKILL.md`, replace:

```markdown
问题说明书(背景/约束/假设/验证标准/可执行改写)的完整方法以 **`xhs-good-question` 为唯一权威源**,本技能不再自带副本。直接告诉用户:「这个问题还没说到可执行——先用『问题说明书』把它说清楚。」转入 `xhs-good-question`。
```

with:

```markdown
问题说明书(背景/约束/假设/验证标准/可执行改写)的完整方法以 **`xhs-good-question` 为唯一权威源**,本技能不再自带副本。直接告诉用户:「这个问题还没说到可执行——先把背景、约束、假设和验证标准说清楚。」然后继续帮助用户把问题改写成可执行版本。
```

Replace:

```markdown
机械环节 vs 判断密集型环节的有益摩擦审计、判断密集型清单,以 **`xhs-slowisfast` 为唯一权威源**,本技能不再重复维护清单。直接提示:「你想省的可能正是产生认知资产的环节——过一遍『慢就是快』审计。」转入 `xhs-slowisfast`。
```

with:

```markdown
机械环节 vs 判断密集型环节的有益摩擦审计、判断密集型清单,以 **`xhs-slowisfast` 为唯一权威源**,本技能不再重复维护清单。直接提示:「你想省的可能正是产生认知资产的环节——先分清哪些步骤能省、哪些判断不能省。」然后继续帮用户做有益摩擦审计。
```

Replace:

```markdown
| 执行力诊断后，问题清楚了但方向不明 | 「执行力不是你的问题，是方向。先看定位。」转入 `xhs-positioning` |
| 问题说明书完成，可以交给 Agent 处理 | 「问题说清楚了，现在可以用对应的工具解决。」 |
```

with:

```markdown
| 执行力诊断后，问题清楚了但方向不明 | 「执行力不是你的问题，是方向。下一步先把账号定位和变现路径说清楚。」 |
| 问题说明书完成，可以继续处理 | 「问题说清楚了，现在可以进入具体处理。」 |
```

- [ ] **Step 7: Run wording contract test**

Run:

```powershell
uv run pytest tests/test_user_visible_skill_language.py -q
```

Expected: PASS.

- [ ] **Step 8: Run existing skill contract tests**

Run:

```powershell
uv run pytest tests/test_dbskill_alias_coverage.py tests/test_xhs_dbskill_productized_skills.py tests/test_grounded_content_contract.py -q
```

Expected: PASS. These guard semantic trigger coverage and grounded content contracts.

- [ ] **Step 9: Commit Task 3 and Task 4 together if no red commit was made**

Run:

```powershell
git add -- tests/test_user_visible_skill_language.py .agents/skills/topic-content/SKILL.md .agents/skills/xhs-copywriting/SKILL.md .agents/skills/xhs-content-system/SKILL.md .agents/skills/xhs-benchmark/SKILL.md .agents/skills/xhs-content/SKILL.md .agents/skills/xhs-action/SKILL.md
git commit -m "fix(skills): hide internal names from user-facing wording"
```

If Task 3 was already committed as a red commit, use:

```powershell
git add -- .agents/skills/topic-content/SKILL.md .agents/skills/xhs-copywriting/SKILL.md .agents/skills/xhs-content-system/SKILL.md .agents/skills/xhs-benchmark/SKILL.md .agents/skills/xhs-content/SKILL.md .agents/skills/xhs-action/SKILL.md
git commit -m "fix(skills): hide internal names from user-facing wording"
```

---

### Task 5: Full Phase 1 Verification

**Files:**
- No code files should be changed in this task unless verification finds a defect.

- [ ] **Step 1: Run full Python tests with a hostile proxy variable**

Run:

```powershell
$env:HTTPS_PROXY='socks5://127.0.0.1:7897'
uv run pytest
```

Expected: PASS with the same skip profile as the current suite. The proxy variable must not cause `socksio` import failures.

- [ ] **Step 2: Run frontend unit tests**

Run:

```powershell
cd web
npm run test:unit
```

Expected: PASS.

- [ ] **Step 3: Run TypeScript check**

Run:

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff for scope creep**

Run:

```powershell
git diff --stat HEAD~3..HEAD
git diff --name-only HEAD~3..HEAD
```

Expected files are limited to:

```text
tests/conftest.py
tests/test_test_environment.py
tests/test_models.py
web/src/lib/tool-render.tsx
web/tests/tool-render.test.ts
tests/test_user_visible_skill_language.py
.agents/skills/topic-content/SKILL.md
.agents/skills/xhs-copywriting/SKILL.md
.agents/skills/xhs-content-system/SKILL.md
.agents/skills/xhs-benchmark/SKILL.md
.agents/skills/xhs-content/SKILL.md
.agents/skills/xhs-action/SKILL.md
```

- [ ] **Step 5: Final commit if verification required small fixes**

If Step 1-4 revealed small fixes, commit them:

```powershell
git add -- tests/conftest.py tests/test_test_environment.py tests/test_models.py web/src/lib/tool-render.tsx web/tests/tool-render.test.ts tests/test_user_visible_skill_language.py .agents/skills/topic-content/SKILL.md .agents/skills/xhs-copywriting/SKILL.md .agents/skills/xhs-content-system/SKILL.md .agents/skills/xhs-benchmark/SKILL.md .agents/skills/xhs-content/SKILL.md .agents/skills/xhs-action/SKILL.md
git commit -m "test: verify phase 1 quality baseline"
```

If no files changed, do not create an empty commit.

---

## Completion Criteria

Phase 1 is complete when:

- `uv run pytest` passes while `HTTPS_PROXY` is set to `socks5://127.0.0.1:7897`.
- `npm run test:unit` passes.
- `tsc --noEmit` passes.
- Frontend thinking labels no longer expose skill slugs.
- Targeted user-facing skill snippets no longer expose internal workflow names.
- Production code paths are not changed for proxy behavior.
