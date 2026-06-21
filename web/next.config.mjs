/** @type {import('next').NextConfig} */
const nextConfig = {
  // 容器化:产出自包含 standalone 运行包(.next/standalone),镜像无需全量 node_modules
  output: "standalone",
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
};

export default nextConfig;
