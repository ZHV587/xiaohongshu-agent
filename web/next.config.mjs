import { resolveStandaloneOutput } from "./next-config-options.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 容器化:产出自包含 standalone 运行包(.next/standalone),镜像无需全量 node_modules。
  // Windows 本地构建常因 pnpm symlink 权限失败,仅本地 win32 禁用 standalone。
  output: resolveStandaloneOutput(),
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
};

export default nextConfig;
