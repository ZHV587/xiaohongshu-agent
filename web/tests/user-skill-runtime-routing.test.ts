import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (file: string) => fs.readFileSync(path.join(root, file), "utf8");

test("explicit user Skill uses the same id for human turn and invocation", () => {
  const provider = read("src/components/thread/ThreadStateProvider.tsx");
  assert.match(provider, /const turnId = uuidv4\(\)/);
  assert.match(provider, /invocation_id:\s*turnId/);
  assert.match(provider, /submitTextForTurn\([\s\S]*turnId/);
  assert.match(provider, /config:\s*\{ configurable:\s*\{ turn_id: newHumanMessage\.id \} \}/);
});

test("custom Skill invocation is generic and not tied to polish", () => {
  const context = read("src/components/thread/ThreadContext.tsx");
  assert.match(context, /executeUserSkill: \(text: string, invocation: UserSkillInvocation\)/);
  assert.match(context, /mode: "execute" \| "test"/);
  const provider = read("src/components/thread/ThreadStateProvider.tsx");
  const section = provider.slice(provider.indexOf("const executeUserSkill"), provider.indexOf("const handleExecuteCommand"));
  assert.doesNotMatch(section, /polish|润色/);
});
