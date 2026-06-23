# Phase 5 Remaining Implementation: Retrieval Ranking & Web Governance

**Date**: 2026-06-23  
**Scope**: Implementation of the remaining Phase 5 features: Retrieval Evidence Ranking (`rank_evidence`), copywriting performance feedback closed-loop, Next.js frontend code splitting, and documentation alignment.

---

## Background

The system now has a complete PostgreSQL data foundation with vector, Meilisearch, and FalkorDB engines. We also have unified Starlette ASGI internal HTTP routes to handle communication from Next.js, and a read-only administrator status page.

However, two major gaps remain in our production-ready checklist:
1. **No Evidence Ranking**: The search results are returned directly from Meilisearch or pgvector without fusing signals, applying recency penalties, incorporating historical post performance (`performance_metric`), or deduplicating.
2. **Monolithic Frontend View**: The main React view `web/src/components/thread/index.tsx` exceeds 78KB, mixing timeline rendering, input text handling, sidebar panels, and state logic.

This design document outlines the exact architecture, code modifications, and testing plan to complete these remaining Phase 5 tasks.

---

## User Review Required

> [!IMPORTANT]
> **Ranking Formula Coefficients & Math Formulation**
> We propose the following linear ranking formula for search results:
> $$Score_{final} = 0.6 \times S_{relevance} + 0.2 \times W_{freshness} + 0.1 \times W_{type} + 0.1 \times W_{performance}$$
> 
> * **Relevance ($S_{relevance}$)**: Normalized vector similarity score ($1 - \text{CosineDistance}$, bounds: $[0.0, 1.0]$) or Meilisearch score normalized by dividing the raw score by the maximum score in the current batch.
> * **Freshness ($W_{freshness}$)**: Modeled using exponential decay:
>   $$W_{freshness} = e^{-0.05 \times t}$$
>   where $t$ is the time delta in days between the current time and `source_updated_at`. If `source_updated_at` is unknown, we assign a fixed penalty of $W_{freshness} = 0.7$.
> * **Resource Type Weight ($W_{type}$)**: 
>   * `performance_metric` / `generated_copy` (best practices & feedback): `1.0`
>   * `generated_topic` (prioritized ideas): `0.8`
>   * Ordinary documents (`doc`, `feishu_doc`): `0.6`
> * **Performance Boost ($W_{performance}$)**: Query the Postgres database for any linked `performance_metric` resource via the `measured_by` edge. The performance score is squashed to $[0.0, 1.0]$ using a hyperbolic tangent function:
>   $$W_{performance} = \tanh\left(\frac{\text{likes} + 2 \times \text{collects} + 5 \times \text{comments}}{500}\right)$$
>   A highly viral post (e.g. 500 likes equivalent) yields $\tanh(1) \approx 0.76$, translating to a near-maximum boost. Missing fields in `content_json` default to `0`.

---

## Detailed Component Specifications

### 1. Deduplication Algorithm
* **Strict Mapping Deduplication**: If two search results share the same `external_id` (from the `resource_mappings` table), they represent the same underlying document. We keep only the candidate with the highest similarity score.
* **Fuzzy Title Deduplication**: For results in the same query batch, if their titles have a sequence similarity ratio $> 0.90$ (computed using Python's standard `difflib.SequenceMatcher`), they are considered duplicates. We keep the one with the higher score.
* **Algorithm Flow**:
  1. Rank raw results by Relevance Score ($S_{relevance}$) in descending order.
  2. Iterate through the ranked list: if the current item is similar to any already-selected item (fuzzy title ratio $> 0.90$ or matching `external_id`), skip it. Otherwise, add it to the final output list.

### 2. Database Bulk Query Optimization
To prevent the $N+1$ query problem when resolving `performance_metric` links for a batch of $N$ resources:
* We will implement a bulk SQL query helper inside `ResourceRepository`:
  ```python
  def bulk_performance_metrics(self, tenant_id: str, resource_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
      # Query linked performance_metric resources using one IN (...) query over resource_edges
  ```
* This reduces database roundtrips to exactly 1 query during evidence ranking.

### 3. Search & Retrieval Context Expansion
* The Python tools `search_resources` and `semantic_search_resources` will output ranked results including:
  ```json
  {
    "resource_id": "...",
    "title": "...",
    "summary": "...",
    "score": 0.892,
    "why_selected": "Matched keyword 'A' in title, refreshed 2 days ago, and has high historical engagement (823 likes).",
    "rank_signals": {
      "relevance": 0.92,
      "freshness": 0.90,
      "performance": 0.85
    }
  }
  ```
* All input limits (`limit` / `top_k`) will be clamped to $[1, 20]$ to avoid over-fetching and performance degradation.
* If a search method fails (e.g. Meilisearch index unavailable or pgvector query raises exception), the ranker handles the exception gracefully, falling back to empty list results instead of crashing the tool execution.

### 4. React Frontend State Provider Pattern
To avoid state mutation conflicts and deep prop-drilling, the split components will communicate via a unified context:
* Create `ThreadContext` inside `web/src/components/thread/ThreadContext.tsx`:
  ```typescript
  interface ThreadState {
    messages: Message[];
    isLoading: boolean;
    isStreaming: boolean;
    activeSidebarView: "feishu" | "evidence" | "facts" | null;
    selectedEvidence: Evidence | null;
  }
  interface ThreadActions {
    sendMessage: (content: string) => Promise<void>;
    selectEvidence: (evidence: Evidence) => void;
    toggleSidebar: (view: "feishu" | "evidence" | "facts" | null) => void;
  }
  ```
* All sub-components (`ChatTimeline`, `ComposerPanel`, `EvidenceInspector`) will import and use the custom hook `useThread()`.

---

## Proposed Changes

### 1. Python Backend Component (Retrieval Ranking & Closed Loop)

#### [NEW] [search_ranker.py](file:///e:/小红书智能体/data_foundation/search_ranker.py)
Create the ranking service that normalizes scores, computes exponential decay for freshness, queries PostgreSQL for performance metrics linked via the `measured_by` edge, performs deduplication on `external_id` and title similarity, and outputs structured `rank_signals` and `why_selected`.

#### [MODIFY] [tools.py](file:///e:/小红书智能体/data_foundation/tools.py)
- Modify `search_resources` and `semantic_search_resources` to invoke the ranking service before returning results.
- Add `rank_signals` and `why_selected` fields to the JSON output payload.

#### [MODIFY] [search.py](file:///e:/小红书智能体/data_foundation/search.py)
Ensure that the results returned by `semantic_search` maintain all necessary metadata fields (such as `source_updated_at` and `updated_at` as `indexed_at`).

---

### 2. Next.js Frontend Component (Structural Governance)

#### [MODIFY] [index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)
- Refactor as `ThreadLayout` container.
- Manage shared state and expose it via `ThreadContext.Provider`.
- Outsource sub-components to separate files.

#### [NEW] [ThreadContext.tsx](file:///e:/小红书智能体/web/src/components/thread/ThreadContext.tsx)
Implements the context state and the `useThread()` custom hook.

#### [NEW] [types.ts](file:///e:/小红书智能体/web/src/components/thread/types.ts)
Expose standard TypeScript definitions for `Message`, `Evidence`, `Topic`, `Copy`, and `RuntimeFact`.

#### [NEW] [ChatTimeline.tsx](file:///e:/小红书智能体/web/src/components/thread/ChatTimeline.tsx)
Render the scrollable list of message bubbles, loader animations, and formatting card views.

#### [NEW] [ComposerPanel.tsx](file:///e:/小红书智能体/web/src/components/thread/ComposerPanel.tsx)
Extract text input box, slash commands triggers, stop generation handles, and files upload states.

#### [NEW] [EvidenceInspector.tsx](file:///e:/小红书智能体/web/src/components/thread/EvidenceInspector.tsx)
A dedicated folding panel rendering search scores, weights, source updates metadata, and the natural language `why_selected` reasoning.

#### [NEW] [RightInspector.tsx](file:///e:/小红书智能体/web/src/components/thread/RightInspector.tsx)
Houses Feishu connection status, wiki space references, and administrator facts view.

---

## Verification Plan

### Automated Tests
- **Python Ranker Tests**:
  * Unit test `test_rank_evidence_formula` verifying mathematical weights.
  * Unit test `test_rank_evidence_deduplication` checking that duplicate title/external mappings are pruned.
  * Integration test `test_rank_evidence_fetches_performance` inserting a `performance_metric` resource and verifying score boost.
  * Run the test suite: `uv run pytest tests/data_foundation/test_search_ranker.py`
- **TypeScript Compilation & Lint**:
  * Validate that the split frontend builds correctly:
    ```bash
    cd web
    .\node_modules\.bin\tsc.CMD --noEmit
    .\node_modules\.bin\eslint.CMD src
    npm run build
    ```

### Manual Verification
- Deploy to the local dev server and trigger a copy-writing query.
- Click the `Evidence` button on a generated copy and confirm that the right folding sidebar displays the custom `why_selected` message and correct ranking details.
