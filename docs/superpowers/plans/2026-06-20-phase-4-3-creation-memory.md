# Phase 4.3 Creation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist generated topics, generated copy, and user feedback into the Postgres data foundation so future content work can retrieve and reuse them.

**Architecture:** Keep DeepAgents as the orchestration layer and expose persistence only through LangChain tools. Generated artifacts are stored as ordinary `resources` with types `generated_topic`, `generated_copy`, and `user_feedback`; evidence links are stored in `resource_edges` from the generated resource to source resources. Repository, outbox, tenant, and actor filtering remain in the existing application service layer.

**Tech Stack:** Python 3.12, DeepAgents, LangChain tools, Postgres resources/resource_edges/resource_outbox, pytest

---

## File Map

- Create `data_foundation/creation_memory.py`: service functions that validate payloads, upsert generated resources, attach evidence edges, and return structured tool payloads.
- Modify `data_foundation/tools.py`: expose `save_generated_topic`, `save_generated_copy`, and `save_user_feedback` as official LangChain tools.
- Modify `agent.py`: no custom runtime changes; the new tools arrive through `phase3_tools`.
- Modify `prompts.py`: require saving generated topics/copy after structured output and saving feedback/revision requests when users modify content.
- Modify `.agents/skills/topic-content/SKILL.md`: mirror the prompt-level save contract.
- Modify `tests/data_foundation/test_tools.py`: tool-level tests for config identity, repository handoff, and tool registration.
- Create `tests/data_foundation/test_creation_memory.py`: service tests for resource type, content JSON shape, edge creation, evidence validation, and no-source cases.
- Modify `tests/test_grounded_content_contract.py`: prompt/skill contract tests for creation-memory tools.
- Modify `tests/test_agent_assembly.py`: agent assembly regression that the new tools are in `phase3_tools`.
- Modify `README.md` and `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`: mark Phase 4.3 implemented after code is green.

## Task 1: Persist Generated Topics And Copy

**Files:**
- Create: `data_foundation/creation_memory.py`
- Create: `tests/data_foundation/test_creation_memory.py`

- [x] **Step 1: Write failing service tests**

Add tests with a fake repository:

```python
def test_save_generated_topic_persists_resource_and_evidence_edges():
    repo = RecordingRepository()

    result = save_generated_topic_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        direction="露营装备",
        topics=["轻量露营（收藏点强）", "亲子露营（决策链短）"],
        evidence=[{"resource_id": "source-1", "summary": "轻量清单收藏高"}],
    )

    assert result["ok"] is True
    assert result["resource"]["type"] == "generated_topic"
    assert repo.upserts[0]["resource_type"] == "generated_topic"
    assert repo.upserts[0]["content_json"]["topics"] == ["轻量露营（收藏点强）", "亲子露营（决策链短）"]
    assert repo.edges == [("generated-1", "source-1", "derived_from")]
```

Add the copy variant:

```python
def test_save_generated_copy_persists_publishable_text_and_evidence_edges():
    repo = RecordingRepository()

    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="露营别乱买",
        body="这份清单够了",
        tags=["#露营", "#装备"],
        source_topic="轻量露营",
        evidence=[{"resource_id": "source-1", "summary": "清单型内容收藏高"}],
    )

    assert result["ok"] is True
    assert repo.upserts[0]["resource_type"] == "generated_copy"
    assert "露营别乱买" in repo.upserts[0]["content_text"]
    assert repo.upserts[0]["content_json"]["tags"] == ["#露营", "#装备"]
    assert repo.edges == [("generated-1", "source-1", "derived_from")]
```

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_creation_memory.py -q
```

Expected: FAIL because `data_foundation.creation_memory` does not exist.

- [x] **Step 3: Implement the service**

Create `data_foundation/creation_memory.py` with:

```python
from __future__ import annotations

from typing import Any

OUTBOX_TOPICS = ["meili_index", "embedding_generate", "graph_ingest"]
DERIVED_EDGE = "derived_from"


def _clean_strings(values: list[str], *, field: str) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty string")
    return cleaned


def _clean_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        resource_id = item.get("resource_id")
        summary = item.get("summary")
        if isinstance(resource_id, str) and resource_id.strip():
            cleaned.append({
                "resource_id": resource_id.strip(),
                "summary": summary.strip() if isinstance(summary, str) and summary.strip() else "",
            })
    return cleaned


def _link_evidence(repo: Any, *, tenant_id: str, generated_id: str, evidence: list[dict[str, str]]) -> None:
    seen: set[str] = set()
    for item in evidence:
        source_id = item["resource_id"]
        if source_id in seen:
            continue
        seen.add(source_id)
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=generated_id,
            target_resource_id=source_id,
            edge_type=DERIVED_EDGE,
            weight=1.0,
        )


def _payload(resource: Any, evidence: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "version": resource.version,
        },
        "evidence_count": len(evidence),
    }


def save_generated_topic_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    direction: str,
    topics: list[str],
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    direction = direction.strip()
    if not direction:
        raise ValueError("direction is required")
    topics = _clean_strings(topics, field="topics")
    cleaned_evidence = _clean_evidence(evidence)
    resource = repo.upsert_resource(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        resource_type="generated_topic",
        title=f"{direction} 选题",
        summary="; ".join(topics[:3]),
        content_text="\n".join(f"- {topic}" for topic in topics),
        content_json={"direction": direction, "topics": topics, "evidence": cleaned_evidence},
        visibility="team",
        owner_open_id=actor_open_id,
        outbox_topics=OUTBOX_TOPICS,
    )
    _link_evidence(repo, tenant_id=tenant_id, generated_id=resource.id, evidence=cleaned_evidence)
    return _payload(resource, cleaned_evidence)
```

Then implement `save_generated_copy_resource(...)` with the same pattern, `resource_type="generated_copy"`, title equal to the generated title, `content_text` as title/body/tags, and `content_json` containing `title`, `body`, `tags`, `source_topic`, and `evidence`.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_creation_memory.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add data_foundation/creation_memory.py tests/data_foundation/test_creation_memory.py
git commit -m "feat: persist generated content resources"
```

## Task 2: Add User Feedback Persistence

**Files:**
- Modify: `data_foundation/creation_memory.py`
- Modify: `tests/data_foundation/test_creation_memory.py`

- [x] **Step 1: Write failing feedback tests**

Add:

```python
def test_save_user_feedback_persists_feedback_and_optional_target_edge():
    repo = RecordingRepository()

    result = save_user_feedback_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        feedback="标题再狠一点",
        target_resource_id="generated-0",
        feedback_type="revision_request",
    )

    assert result["ok"] is True
    assert repo.upserts[0]["resource_type"] == "revision_request"
    assert repo.edges == [("generated-1", "generated-0", "feedback_on")]
```

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_creation_memory.py::test_save_user_feedback_persists_feedback_and_optional_target_edge -q
```

Expected: FAIL because `save_user_feedback_resource` does not exist.

- [x] **Step 3: Implement feedback service**

Add:

```python
def save_user_feedback_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    feedback: str,
    target_resource_id: str | None = None,
    feedback_type: str = "user_feedback",
) -> dict[str, Any]:
    feedback = feedback.strip()
    if not feedback:
        raise ValueError("feedback is required")
    if feedback_type not in {"user_feedback", "revision_request"}:
        raise ValueError("feedback_type must be user_feedback or revision_request")
    resource = repo.upsert_resource(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        resource_type=feedback_type,
        title="用户反馈" if feedback_type == "user_feedback" else "修改意见",
        summary=feedback[:120],
        content_text=feedback,
        content_json={"feedback": feedback, "target_resource_id": target_resource_id},
        visibility="team",
        owner_open_id=actor_open_id,
        outbox_topics=OUTBOX_TOPICS,
    )
    if target_resource_id:
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=resource.id,
            target_resource_id=target_resource_id,
            edge_type="feedback_on",
            weight=1.0,
        )
    return _payload(resource, [])
```

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_creation_memory.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add data_foundation/creation_memory.py tests/data_foundation/test_creation_memory.py
git commit -m "feat: persist content feedback resources"
```

## Task 3: Expose Creation Memory As Official Tools

**Files:**
- Modify: `data_foundation/tools.py`
- Modify: `tests/data_foundation/test_tools.py`
- Modify: `tests/test_agent_assembly.py`

- [x] **Step 1: Write failing tool tests**

Add tests that monkeypatch `_repository` and call:

```python
result = df_tools.save_generated_topic.func(
    direction="露营装备",
    topics=["轻量露营（收藏点强）"],
    evidence=[{"resource_id": "source-1", "summary": "依据"}],
    config=identity_config("ou_user"),
)
```

Assert the service receives `tenant_id="default"` and `actor_open_id="ou_user"`.

Add assembly regression:

```python
assert {"save_generated_topic", "save_generated_copy", "save_user_feedback"} <= tool_names
```

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/data_foundation/test_tools.py tests/test_agent_assembly.py -q
```

Expected: FAIL because the tools are not registered.

- [x] **Step 3: Implement tools**

In `data_foundation/tools.py`, import the three service functions and add:

```python
@tool
def save_generated_topic(direction: str, topics: list[str], evidence: list[dict[str, Any]] | None = None, config: RunnableConfig | None = None) -> dict[str, Any]:
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_generated_topic_resource(repo, tenant_id=default_tenant_id(), actor_open_id=actor, direction=direction, topics=topics, evidence=evidence)
```

Add equivalent `save_generated_copy(...)` and `save_user_feedback(...)`, then append all three to `data_foundation_tools`.

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/data_foundation/test_tools.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add data_foundation/tools.py tests/data_foundation/test_tools.py tests/test_agent_assembly.py
git commit -m "feat: expose creation memory tools"
```

## Task 4: Require Creation Memory In Agent Contracts

**Files:**
- Modify: `prompts.py`
- Modify: `.agents/skills/topic-content/SKILL.md`
- Modify: `tests/test_grounded_content_contract.py`

- [x] **Step 1: Write failing contract tests**

Extend required tools to include:

```python
{"save_generated_topic", "save_generated_copy", "save_user_feedback"}
```

Assert the contracts say generated topics are saved after `xhs_topics`, generated copy is saved after `xhs_copy`, and revision/user feedback is saved through `save_user_feedback`.

- [x] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_grounded_content_contract.py -q
```

Expected: FAIL because contracts do not mention the new save tools.

- [x] **Step 3: Update prompt and skill**

After the `xhs_topics` code block instruction, add:

```text
输出选题卡后调用 `save_generated_topic`,保存 direction、topics 和实际 evidence。
```

After the `xhs_copy` code block instruction, add:

```text
输出完整文案后调用 `save_generated_copy`,保存 title、body、tags、source_topic 和 evidence。
```

In the revision section, add:

```text
用户提出修改意见时,先调用 `save_user_feedback` 保存反馈或 revision_request,再继续打磨。
```

- [x] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_grounded_content_contract.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add prompts.py .agents/skills/topic-content/SKILL.md tests/test_grounded_content_contract.py
git commit -m "feat: require creation memory in content workflow"
```

## Task 5: Documentation And Full Regression

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`
- Modify: this plan

- [x] **Step 1: Update docs**

Mark Phase 4.3 implemented and describe the three tools, resource types, and edges:

- `save_generated_topic` -> `generated_topic`
- `save_generated_copy` -> `generated_copy`
- `save_user_feedback` -> `user_feedback` or `revision_request`
- `derived_from` and `feedback_on` edges

- [x] **Step 2: Run focused regression**

```bash
uv run pytest tests/data_foundation/test_creation_memory.py tests/data_foundation/test_tools.py tests/test_grounded_content_contract.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [x] **Step 3: Run full regression**

```bash
uv run pytest -q
cd web
npm run test:unit
npx tsc --noEmit
npm run lint
```

Expected: PASS, allowing existing frontend lint warnings.

- [x] **Step 4: Review and commit**

```bash
git diff --check
git status --short
git add README.md docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md docs/superpowers/plans/2026-06-20-phase-4-3-creation-memory.md
git commit -m "docs: document creation memory loop"
git push origin master
```

---

## Self-Review

**Spec coverage:** Phase 4.3 asks for generated topics, generated copy, user feedback, edges from generated resources to sources, and traceable creation events. Tasks 1-3 implement those capabilities through service functions and official tools; Task 4 makes the Agent workflow use them; Task 5 documents completion.

**Official-framework boundary:** All Agent-facing behavior is exposed through LangChain tools registered in `create_deep_agent(tools=[...])`. Postgres writes remain behind repository/service code. No CLI, private DeepAgents mutation, management backend, or direct SQL access from prompts is introduced.

**Type consistency:** Resource types are `generated_topic`, `generated_copy`, `user_feedback`, and `revision_request`. Edge types are `derived_from` and `feedback_on`. Tool names are `save_generated_topic`, `save_generated_copy`, and `save_user_feedback`.

**Placeholder scan:** No TODO/TBD placeholders remain in the plan.
