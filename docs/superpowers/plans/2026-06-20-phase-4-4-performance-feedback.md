# Phase 4.4 Performance Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist published-content performance metrics into the Postgres data foundation and make them available to future retrieval and graph expansion.

**Architecture:** Keep Postgres as the authoritative store and DeepAgents as orchestration. Performance data is stored as ordinary `resources` with type `performance_metric`, linked to generated or source content through `resource_edges` edge type `measured_by`; high/low performance is represented as an explainable score in `content_json` and edge weight. Agent-facing access is only through LangChain tools.

**Tech Stack:** Python 3.12, DeepAgents, LangChain tools, Postgres resources/resource_edges/resource_outbox, pytest

---

## File Map

- Create `data_foundation/performance_feedback.py`: service functions to normalize metrics, compute an explainable score, persist `performance_metric`, and link to target content.
- Modify `data_foundation/tools.py`: expose `save_performance_metric` and `get_resource_performance` as official LangChain tools.
- Modify `data_foundation/repository.py`: add a read method for performance metrics by target resource.
- Create `tests/data_foundation/test_performance_feedback.py`: service and real-repository tests.
- Modify `tests/data_foundation/test_tools.py`: tool registration and actor/tenant handoff tests.
- Modify `tests/test_agent_assembly.py`: assert the new tools are registered in `phase3_tools`.
- Modify `prompts.py` and `.agents/skills/topic-content/SKILL.md`: require querying performance when judging past performance and saving metrics when user provides post-publish data.
- Modify `tests/test_grounded_content_contract.py`: contract tests for performance tools.
- Modify `README.md` and `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`: mark Phase 4.4 implemented.

## Task 1: Persist Performance Metric Resources

**Files:**
- Create `data_foundation/performance_feedback.py`
- Create `tests/data_foundation/test_performance_feedback.py`

- [x] **Step 1: Write failing service tests**

Add:

```python
def test_save_performance_metric_persists_metric_and_measured_by_edge():
    repo = RecordingRepository()

    result = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        target_resource_id="generated-1",
        metrics={"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
        published_at="2026-06-20T08:00:00+00:00",
        channel="xiaohongshu",
        note_url="https://example.com/note/1",
    )

    assert result["ok"] is True
    assert repo.upserts[0]["resource_type"] == "performance_metric"
    assert repo.upserts[0]["content_json"]["score"] > 0
    assert repo.edges == [("generated-1", "metric-1", "measured_by", repo.upserts[0]["content_json"]["score"])]
```

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_performance_feedback.py -q
```

Expected: FAIL because `data_foundation.performance_feedback` does not exist.

- [x] **Step 3: Implement service**

Implement:

- allowed metrics: `likes`, `collects`, `comments`, `shares`, `views`, `conversions`
- score formula: `likes + 2*collects + 3*comments + 4*shares + 5*conversions`, divided by `max(views, 1)` when `views` exists, rounded to 6 decimals
- resource type `performance_metric`
- edge from target resource to metric resource with edge type `measured_by` and weight equal to score
- one transaction through `repo.unit_of_work()`

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_performance_feedback.py -q
```

Expected: PASS.

## Task 2: Read Performance For A Resource

**Files:**
- Modify `data_foundation/repository.py`
- Modify `data_foundation/performance_feedback.py`
- Modify `tests/data_foundation/test_performance_feedback.py`

- [x] **Step 1: Write failing read tests**

Add a fake repository test for `get_resource_performance_payload(...)`, and a migrated Postgres test that saves a metric then reads it back by target resource.

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_performance_feedback.py -q
```

Expected: FAIL because repository read method does not exist.

- [x] **Step 3: Implement repository read**

Add `ResourceRepository.performance_rows(...)` that:

- uses `readable_resource_where("target")` for the target content
- joins `resource_edges` from target to metric resource with `edge_type='measured_by'`
- returns metric resource id/title/content_json/edge weight/updated_at
- orders by metric resource `updated_at desc`

- [x] **Step 4: Implement service payload**

Return:

```python
{"ok": True, "target_resource_id": "...", "metrics": [{"resource_id": "...", "score": 0.1, "metrics": {...}}]}
```

- [x] **Step 5: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_performance_feedback.py -q
```

Expected: PASS.

## Task 3: Expose Performance Tools

**Files:**
- Modify `data_foundation/tools.py`
- Modify `tests/data_foundation/test_tools.py`
- Modify `tests/test_agent_assembly.py`

- [x] **Step 1: Write failing tool tests**

Assert `save_performance_metric` and `get_resource_performance` exist, use `actor_from_config`, and pass `tenant_id/default` plus current actor to service/repository.

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_tools.py tests/test_agent_assembly.py -q
```

Expected: FAIL because tools are not registered.

- [x] **Step 3: Implement LangChain tools**

Add:

- `save_performance_metric(target_resource_id, metrics, published_at=None, channel="xiaohongshu", note_url=None, config=None)`
- `get_resource_performance(resource_id, config=None)`

Append both to `data_foundation_tools`.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_tools.py tests/test_agent_assembly.py -q
```

Expected: PASS.

## Task 4: Update Agent Contracts

**Files:**
- Modify `prompts.py`
- Modify `.agents/skills/topic-content/SKILL.md`
- Modify `tests/test_grounded_content_contract.py`

- [x] **Step 1: Write failing contract tests**

Require both contracts to mention `save_performance_metric` and `get_resource_performance`, and to say:

- when user provides post-publish likes/collects/comments/views, call `save_performance_metric`
- when user asks “过去表现如何/为什么推荐”, call `get_resource_performance` for relevant resources

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_grounded_content_contract.py -q
```

Expected: FAIL.

- [x] **Step 3: Update contracts**

Add a short section to prompt and skill: performance feedback is data, not prose; save it through tools and retrieve it when reasoning about past performance.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_grounded_content_contract.py -q
```

Expected: PASS.

## Task 5: Documentation, Review, And Full Regression

**Files:**
- Modify `README.md`
- Modify `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`
- Modify this plan

- [x] **Step 1: Update docs**

Mark Phase 4.4 implemented and document:

- `performance_metric`
- `measured_by`
- explainable score formula
- no predictive model in first version

- [x] **Step 2: Run regression**

```bash
uv run pytest -q
cd web
npm run test:unit
npx tsc --noEmit
npm run lint
git diff --check
```

- [x] **Step 3: Request code review**

Ask a review agent to inspect Phase 4.4 diff for correctness, tool boundaries, score semantics, and tests.

Review remediation completed:

- `save_performance_metric` now requires write access to the target resource before saving feedback.
- Performance metric resources inherit target visibility and owner instead of defaulting to team visibility.
- `get_resource_performance` filters both target and metric resources through actor-readable predicates.
- Metrics reject invalid, NaN, infinite, and negative values with stable validation errors.
- Prompt and skill now require the current generated copy ID when available, and require asking the user rather than guessing when the target content is unknown.

- [x] **Step 4: Commit and push**

```bash
git add -A
git commit -m "feat: persist performance feedback"
git push origin master
```

---

## Self-Review

**Spec coverage:** Phase 4.4 requires `performance_metric`, graph edges to effects, retrieval-time access to performance, and explainable weighting. Tasks 1-4 implement these without adding a prediction model.

**Official-framework boundary:** Agent access is only via LangChain tools registered in `create_deep_agent`; all Postgres mutation stays in application services and repository code.

**Type consistency:** Resource type is `performance_metric`; edge type is `measured_by`; tools are `save_performance_metric` and `get_resource_performance`.

**Placeholder scan:** No placeholders remain.
