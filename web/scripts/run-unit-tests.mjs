import { spawnSync } from "node:child_process";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const outputDir = await mkdtemp(join(tmpdir(), "xhs-web-unit-"));
const testEntries = [
  join(webRoot, "src/lib/xhs-blocks.test.ts"),
  ...(await readdir(join(webRoot, "tests")))
    .filter((name) => name.endsWith(".test.ts"))
    .sort()
    .map((name) => join(webRoot, "tests", name)),
];
const outputFiles = testEntries.map((_, index) => join(outputDir, `unit-${index}.test.cjs`));

try {
  for (const [index, entry] of testEntries.entries()) {
    await build({
      entryPoints: [entry],
      outfile: outputFiles[index],
      bundle: true,
      platform: "node",
      format: "cjs",
      tsconfig: join(webRoot, "tsconfig.json"),
    });
  }

  const result = spawnSync(process.execPath, ["--test", ...outputFiles], {
    cwd: webRoot,
    stdio: "inherit",
  });

  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  await rm(outputDir, { recursive: true, force: true });
}
