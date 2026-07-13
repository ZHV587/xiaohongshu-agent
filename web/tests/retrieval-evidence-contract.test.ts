import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const read = (...parts: string[]) => readFileSync(join(process.cwd(), ...parts), "utf8");

test("frontend exposes one unified knowledge retrieval tool", () => {
  const trace = read("src", "lib", "agent-trace.ts");
  const thinking = read("src", "lib", "thinking-trace.ts");
  const runtime = `${trace}\n${thinking}`;

  assert.match(runtime, /retrieve_knowledge/);
  for (const removed of ["semantic_search_resources", "search_resources", "graph_expand"]) {
    assert.ok(!runtime.includes(removed), `removed retrieval tool leaked into frontend runtime: ${removed}`);
  }
});

test("xhs topic evidence accepts only the four-state retrieval_mode contract", () => {
  const blocks = read("src", "lib", "xhs-blocks.ts");
  assert.match(blocks, /retrieval_mode\?: RetrievalMode/);
  for (const mode of ["hybrid", "semantic_only", "keyword_only", "insufficient_relevance"]) {
    assert.ok(blocks.includes(`"${mode}"`), `missing retrieval mode: ${mode}`);
  }
  assert.ok(!blocks.includes("evidence_mode"), "removed evidence_mode must not be parsed");
});

test("studio renders authoritative quality without zero-value fabrication", () => {
  const context = read("src", "components", "studio", "StudioContext.tsx");
  const screen = read("src", "components", "studio", "CreationScreen.tsx");

  assert.match(context, /quality: e\.quality/);
  assert.doesNotMatch(context, /quality:\s*e\.quality\s*\?\?/);
  assert.match(screen, /知识质量 Quality/);
  assert.match(screen, /相关证据不足/);
  assert.match(screen, /resource_id}:\$\{it\.resource_version/);
});
