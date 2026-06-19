# Phase 4.2 Retrieval-Grounded Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make topic and copy generation consistently retrieve from the Postgres data foundation, expose concise source evidence to users, and explicitly degrade when usable data is missing.

**Architecture:** Keep DeepAgents as the orchestration layer: the main agent and `baokuan-analyst` receive existing LangChain data-foundation tools through `tools`, the `topic-content` skill defines the retrieval-first workflow, and `RubricMiddleware` checks grounding and freshness. Postgres remains behind application-service tools; the Web client only parses and presents the structured evidence emitted by the LLM.

**Tech Stack:** Python 3.12, DeepAgents, LangChain tools, pytest, React 19, TypeScript 5, Next.js 15, esbuild, Node test runner

---

## File Map

- `data_foundation/search.py`: include resource freshness in search-result metadata.
- `data_foundation/tools.py`: return freshness from full-resource reads.
- `prompts.py`: define the retrieval-first creation flow, evidence JSON contract, and no-data degradation behavior.
- `.agents/skills/topic-content/SKILL.md`: make the official DeepAgents skill match the main prompt contract.
- `subagents.py`: give `baokuan-analyst` the unified retrieval tools and evidence-oriented analysis instructions.
- `agent.py`: strengthen the existing official `RubricMiddleware` policy.
- `web/src/lib/xhs-blocks.ts`: preserve validated evidence in structured topic/copy segments.
- `web/src/components/thread/messages/topic-cards.tsx`: show compact source summaries under topic choices.
- `web/src/components/thread/messages/copy-card.tsx`: show compact source summaries without including them in copied copy text.
- `web/src/lib/xhs-blocks.test.ts`: parser regressions for evidence and malformed optional evidence.
- `web/scripts/run-unit-tests.mjs`: bundle TypeScript tests with installed esbuild and execute them with Node.
- `tests/data_foundation/test_search_graph_tools.py`: freshness payload regressions.
- `tests/test_grounded_content_contract.py`: prompt and skill contract regressions.
- `tests/test_subagents.py`: subagent prompt/tool regressions.
- `tests/test_agent_assembly.py`: rubric policy regression.
- `README.md` and Phase 4 spec: document completion and runtime behavior.

### Task 1: Expose Source Freshness Through Retrieval Tools

**Files:**
- Modify: `data_foundation/search.py`
- Modify: `data_foundation/tools.py`
- Modify: `tests/data_foundation/test_search_graph_tools.py`

- [ ] **Step 1: Write failing tests**

Add a row-level test asserting `_result_from_row(...)` serializes `updated_at` as ISO 8601 in `metadata`, and a tool test asserting `get_resource` returns `updated_at` beside `version`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/data_foundation/test_search_graph_tools.py -q`

Expected: FAIL because freshness is absent from both payloads.

- [ ] **Step 3: Implement the minimum payload changes**

In `_result_from_row`, add:

```python
updated_at = row.get("updated_at") if hasattr(row, "get") else row["updated_at"]
if updated_at is not None:
    metadata["updated_at"] = updated_at.isoformat()
```

In `get_resource`, add:

```python
"updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
```

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/data_foundation/test_search_graph_tools.py -q`

Expected: PASS, with database-backed cases skipped when `TEST_XHS_DATABASE_URL` is absent.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/search.py data_foundation/tools.py tests/data_foundation/test_search_graph_tools.py
git commit -m "feat: expose resource freshness to agents"
```

### Task 2: Make Main Prompt And Skill Retrieval-First

**Files:**
- Create: `tests/test_grounded_content_contract.py`
- Modify: `prompts.py`
- Modify: `.agents/skills/topic-content/SKILL.md`

- [ ] **Step 1: Write failing contract tests**

Create tests that read both contracts and assert they contain:

```python
REQUIRED_TOOLS = {
    "search_resources",
    "semantic_search_resources",
    "graph_expand",
    "get_resource",
    "sync_feishu_resources",
}
```

Also assert both define an `evidence` array with `resource_id`, `title`, `summary`, and `updated_at`, state that direct Feishu reads are fallback-only, and contain the exact user-facing phrase `当前数据不足`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_grounded_content_contract.py -q`

Expected: FAIL because the current contracts are Feishu-first and have no evidence schema.

- [ ] **Step 3: Update the main prompt**

Specify this order:

1. Call `search_resources` first.
2. Optionally call `semantic_search_resources`; failure must fall back to keyword results.
3. Use `get_resource` for selected source details and `graph_expand` only when related context adds value.
4. Use direct Feishu reads only when unified results are empty and explain that they are fallback data.
5. When no usable source remains, say `当前数据不足`, recommend `sync_feishu_resources` or additional data, and do not output fabricated claims.

Extend both fenced JSON examples with:

```json
"evidence": [{"resource_id": "资源ID", "title": "来源标题", "summary": "支持本次创作的关键依据", "updated_at": "2026-06-19T12:30:00+00:00"}]
```

- [ ] **Step 4: Update the official skill**

Mirror the same retrieval order, fallback rule, degradation phrase, and evidence schema in `.agents/skills/topic-content/SKILL.md`.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/test_grounded_content_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts.py .agents/skills/topic-content/SKILL.md tests/test_grounded_content_contract.py
git commit -m "feat: ground content workflow in unified retrieval"
```

### Task 3: Equip The Analyst Subagent With Unified Retrieval

**Files:**
- Create: `tests/test_subagents.py`
- Modify: `subagents.py`

- [ ] **Step 1: Write failing tests**

Build the analyst with existing model fixtures or lightweight stubs and assert its tool names include:

```python
{"search_resources", "semantic_search_resources", "graph_expand", "get_resource"}
```

Assert `ANALYST_SYSTEM_PROMPT` prioritizes `search_resources`, treats Feishu tools as fallback, records source IDs and freshness, and explicitly reports insufficient data.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_subagents.py -q`

Expected: FAIL because the subagent only has direct Feishu tools.

- [ ] **Step 3: Implement the official subagent extension**

Import the four retrieval tools from `data_foundation.tools`, add them to the subagent `tools` list before the Feishu fallback tools, and revise the prompt/description to produce an evidence section containing source ID, title, summary, and freshness.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_subagents.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add subagents.py tests/test_subagents.py
git commit -m "feat: add unified retrieval to analyst subagent"
```

### Task 4: Strengthen Rubric Grounding Checks

**Files:**
- Modify: `tests/test_agent_assembly.py`
- Modify: `agent.py`

- [ ] **Step 1: Write a failing assembly test**

Extend the capturing `RubricMiddleware` test double to retain `system_prompt`, then assert the rubric checks all four policies: source evidence, source freshness, unsupported claims, and explicit insufficient-data degradation.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_agent_assembly.py -q`

Expected: FAIL because the current rubric only says content should have data support.

- [ ] **Step 3: Update the rubric prompt**

Keep existing style checks and add concrete rejection criteria:

- topics/copy must include evidence summaries and resource IDs when data is used;
- stale `updated_at` values must not be presented as current facts without qualification;
- claims not supported by retrieved content must be removed or labeled as creative inference;
- when sources are empty or unusable, the response must say `当前数据不足` and suggest sync/additional data.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_agent_assembly.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent_assembly.py
git commit -m "feat: enforce grounding in content rubric"
```

### Task 5: Preserve And Render Evidence In Web Cards

**Files:**
- Create: `web/src/lib/xhs-blocks.test.ts`
- Create: `web/scripts/run-unit-tests.mjs`
- Modify: `web/package.json`
- Modify: `web/src/lib/xhs-blocks.ts`
- Modify: `web/src/components/thread/messages/topic-cards.tsx`
- Modify: `web/src/components/thread/messages/copy-card.tsx`

- [ ] **Step 1: Add the TypeScript unit-test runner**

Use the installed `esbuild` JavaScript API to bundle `src/lib/xhs-blocks.test.ts` to a temporary directory, execute it with `node --test`, propagate the exit code, and remove the temporary directory in `finally`. Add `"test:unit": "node scripts/run-unit-tests.mjs"` to `package.json`.

- [ ] **Step 2: Write failing parser tests**

Test that valid topic and copy evidence survives parsing, malformed evidence entries are filtered, and payloads without evidence remain backward compatible with `evidence: []`.

- [ ] **Step 3: Verify RED**

Run from `web`: `npm run test:unit`

Expected: FAIL because the parser drops evidence.

- [ ] **Step 4: Add the evidence type and parser**

Define:

```typescript
export interface SourceEvidence {
  resource_id: string;
  title: string;
  summary: string;
  updated_at?: string;
}
```

Add `evidence: SourceEvidence[]` to both segment data shapes. Parse only objects with non-empty string `resource_id`, `title`, and `summary`; preserve optional string `updated_at`; return `[]` when absent or invalid. Partial streaming output may keep `evidence: []` until complete JSON is available.

- [ ] **Step 5: Render compact evidence sections**

Under each card's primary content, render a single un-nested evidence section labeled `创作依据`, listing source title and summary. Use `Database` from `lucide-react`; keep evidence out of `CopyCard.fullText` so one-click copy only copies publishable content.

- [ ] **Step 6: Verify GREEN and type safety**

Run from `web`:

```bash
npm run test:unit
npx tsc --noEmit
npm run lint -- src
```

Expected: unit tests and TypeScript pass; lint has no new errors.

- [ ] **Step 7: Commit**

```bash
git add web/package.json web/scripts/run-unit-tests.mjs web/src/lib/xhs-blocks.test.ts web/src/lib/xhs-blocks.ts web/src/components/thread/messages/topic-cards.tsx web/src/components/thread/messages/copy-card.tsx
git commit -m "feat: display content source evidence"
```

### Task 6: Documentation, Self-Review, And Full Regression

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`

- [ ] **Step 1: Document Phase 4.2 behavior**

Document retrieval-first creation, visible source summaries, semantic-to-keyword fallback, explicit insufficient-data behavior, and the unchanged official DeepAgents extension boundary.

- [ ] **Step 2: Update Phase 4 status**

Mark Phase 4.2 complete while leaving 4.3-4.5 pending.

- [ ] **Step 3: Run focused regression**

```bash
uv run pytest tests/test_grounded_content_contract.py tests/test_subagents.py tests/test_agent_assembly.py tests/data_foundation/test_search_graph_tools.py -q
```

Expected: PASS, allowing configured Postgres integration skips.

- [ ] **Step 4: Run full regression**

```bash
uv run pytest -q
cd web
npm run test:unit
npx tsc --noEmit
npm run lint -- src
```

Expected: backend and frontend checks pass with no new warnings.

- [ ] **Step 5: Inspect changes**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors and only intended Phase 4.2 files are modified.

- [ ] **Step 6: Commit and push**

```bash
git add README.md docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md
git commit -m "docs: document retrieval-grounded content loop"
git push origin master
```

---

## Self-Review

**Spec coverage:** Task 2 makes the skill retrieval-first and adds no-data degradation; Task 5 carries key evidence summaries to the visible Web response; Task 4 checks grounding, freshness, and fabrication; Tasks 1 and 3 give the LLM the freshness and unified tools required to satisfy those policies.

**Official-framework boundary:** All Agent-facing behavior stays in DeepAgents `tools`, `skills`, `subagents`, and `middleware`. Postgres remains behind LangChain tools, the Web remains the only business entry, and no CLI, management backend, private graph mutation, or database access from prompts/components is introduced.

**Type consistency:** The evidence contract is consistently named `evidence` with `resource_id`, `title`, `summary`, and optional `updated_at` in prompts, skill, parser, and cards. Retrieval freshness is consistently ISO 8601.

**Placeholder scan:** No deferred implementation markers or unspecified error-handling steps remain.
