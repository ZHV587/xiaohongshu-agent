# 小红书智能体 Web(Next.js 15)生产镜像 —— 多阶段 + standalone
# 用 npm 构建(对齐服务器现状与 CLAUDE.md);output:standalone 产出自包含运行包。

# ---- deps:装依赖(含 dev,build 需要)----
FROM node:20-alpine AS deps
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
COPY package.json package-lock.json ./
RUN npm ci

# ---- builder:构建 ----
FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* 在 build 时内联进客户端 bundle,必须在此提供(运行时注入对客户端无效)。
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ASSISTANT_ID
ARG NEXT_PUBLIC_AUTH_SCHEME
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ASSISTANT_ID=$NEXT_PUBLIC_ASSISTANT_ID
ENV NEXT_PUBLIC_AUTH_SCHEME=$NEXT_PUBLIC_AUTH_SCHEME
RUN npm run build

# ---- runner:仅 standalone 产物,最小镜像 ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# standalone 自带最小 node_modules 与 server.js;static 与 public 需单独拷入
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
