import { spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const outputDir = await mkdtemp(join(tmpdir(), "xhs-web-unit-"));
const outputFile = join(outputDir, "xhs-blocks.test.cjs");

try {
  await build({
    entryPoints: [join(webRoot, "src/lib/xhs-blocks.test.ts")],
    outfile: outputFile,
    bundle: true,
    platform: "node",
    format: "cjs",
  });

  const result = spawnSync(process.execPath, ["--test", outputFile], {
    cwd: webRoot,
    stdio: "inherit",
  });

  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  await rm(outputDir, { recursive: true, force: true });
}
