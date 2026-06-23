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
> **Ranking Formula Coefficients**
> We propose the following linear ranking formula for search results:
> $$Score_{final} = 0.6 \times S_{relevance} + 0.2 \times W_{freshness} + 0.1 \times W_{type} + 0.1 \times W_{performance}$$
> - **Relevance ($S_{relevance}$)**: Normalized vector similarity distance or Meilisearch rating (0.0 to 1.0).
> - **Freshness ($W_{freshness}$)**: Exponential decay based on days since `source_updated_at`. If `source_updated_at` is unknown, apply a fixed multiplier penalty of `0.7`.
> - **Resource Type ($W_{type}$)**: `1.0` for performance metrics or generated copies, `0.8` for topic cards, and `0.6` for ordinary documents.
> - **Performance ($W_{performance}$)**: Scaled performance index (0.0 to 1.0) derived from linked `performance_metric` (likes, collections, shares). Max boost is `0.2` if the metrics show high user engagement.

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
- Manage shared state and expose it via a React Context (`ThreadContext`).
- Outsource sub-components to separate files.

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
