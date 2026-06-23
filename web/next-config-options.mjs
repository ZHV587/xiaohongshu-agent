export function resolveStandaloneOutput(platform = process.platform) {
  return platform === "win32" ? undefined : "standalone";
}
