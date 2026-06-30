"use client";

// useBackendResource — the single data-fetching primitive behind every 账号运营
// collection (看板 / 日历 / 账号矩阵 / 发布管线 / 最近创作 / 趋势). It fetches a
// same-origin BFF route under /api/backend/* and exposes a uniform LoadState so
// each panel can render loading / empty / error consistently.
//
// 真实数据铁律（需求 16.1 / 16.3）：
//   • fallback 只能是空容器（[] 或 {}），绝不含任何 mock 业务值。
//   • 后端返回空集合 → status="empty"（UI 渲染空态文案，不渲染 0 值卡片）。
//   • fetch 失败 / 非 2xx / 5xx / 解析失败 → status="error"，data 保持空 fallback，
//     绝不回退到占位或编造数值。
// 该 hook 为纯前端数据获取封装，不持有任何业务默认值。

import { useCallback, useEffect, useRef, useState } from "react";

export type LoadStatus = "idle" | "loading" | "ready" | "empty" | "error";

export interface LoadState<T> {
  /** 当前数据。请求未就绪 / 出错时恒为传入的空 fallback（[] 或 {}）。 */
  data: T;
  status: LoadStatus;
  /** 仅在 status==="error" 时存在，供 UI 展示错误态文案。 */
  error?: string;
  /** 手动重新拉取（如重试按钮）。account 变化已自动触发，无需手动调用。 */
  reload: () => void;
}

/**
 * 判断后端返回的数据是否为「空集合」。默认规则：
 *   • null / undefined → 空
 *   • 数组 → 长度为 0 即空
 *   • 字符串 → 去空白后为空即空
 *   • 对象 → 无键，或所有值递归为空即空
 *   • 数字 / 布尔 → 非空
 * 业务面板若需更精确的空态判定（如以某个键为准），可通过 options.isEmpty 覆盖。
 */
function isEmptyDefault(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "string") return value.trim().length === 0;
  if (typeof value === "object") {
    const values = Object.values(value as Record<string, unknown>);
    if (values.length === 0) return true;
    return values.every((v) => isEmptyDefault(v));
  }
  return false;
}

export interface UseBackendResourceOptions<T> {
  /** 自定义空态判定，覆盖默认规则（见 isEmptyDefault）。 */
  isEmpty?: (data: T) => boolean;
}

/**
 * 统一加载 /api/backend/* 资源，提供 loading / empty / error / ready 四态。
 *
 * @param path     同源 BFF 路径，如 "/api/backend/analytics"。
 * @param fallback 空数据默认值（[] 或 {}）。绝不含 mock 业务值。
 * @param params   可选查询参数（如 { account: "acc_1" }）。account 变化时自动重拉。
 * @param options  可选项（如自定义 isEmpty）。
 */
export function useBackendResource<T>(
  path: string,
  fallback: T,
  params?: Record<string, string | undefined>,
  options?: UseBackendResourceOptions<T>,
): LoadState<T> {
  const [data, setData] = useState<T>(fallback);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [error, setError] = useState<string | undefined>(undefined);
  const [reloadTick, setReloadTick] = useState(0);

  // 保持 fallback / isEmpty 引用稳定，避免把它们放进 effect 依赖导致无谓重拉。
  const fallbackRef = useRef(fallback);
  fallbackRef.current = fallback;
  const isEmptyRef = useRef(options?.isEmpty);
  isEmptyRef.current = options?.isEmpty;

  // 仅以「有效参数」的序列化结果作为依赖，过滤掉 undefined 值（如未选账号）。
  const queryKey = serializeParams(params);

  const reload = useCallback(() => setReloadTick((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let alive = true;

    setStatus("loading");
    setError(undefined);

    const url = queryKey ? `${path}?${queryKey}` : path;

    fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (!res.ok) {
          // 非 2xx（含 4xx 鉴权失败 / 5xx 服务端错误）→ 错误态，不回退占位。
          throw new Error(`请求失败（${res.status}）`);
        }
        const body = (await res.json()) as unknown;
        // 后端约定写接口用 { ok: false, error } 报错；GET 一般直接返回数据，
        // 但若显式带 ok:false 也按错误态处理。
        if (body && typeof body === "object" && (body as { ok?: boolean }).ok === false) {
          const msg = (body as { error?: string }).error;
          throw new Error(msg || "后端返回错误");
        }
        return body as T;
      })
      .then((body) => {
        if (!alive) return;
        const empty = isEmptyRef.current ? isEmptyRef.current(body) : isEmptyDefault(body);
        if (empty) {
          // 空集合：data 保持空 fallback，状态置 empty 供 UI 渲染空态文案。
          setData(fallbackRef.current);
          setStatus("empty");
        } else {
          setData(body);
          setStatus("ready");
        }
      })
      .catch((err: unknown) => {
        if (!alive || controller.signal.aborted) return;
        // fetch 失败 / 5xx / 解析失败 → 错误态，data 回到空 fallback，绝不编造数值。
        setData(fallbackRef.current);
        setError(err instanceof Error ? err.message : "未知错误");
        setStatus("error");
      });

    return () => {
      alive = false;
      controller.abort();
    };
    // path / 有效参数 / 手动 reload 任一变化都重新拉取（account 变化即在此触发）。
  }, [path, queryKey, reloadTick]);

  return { data, status, error, reload };
}

/** 将参数序列化为稳定的查询串，跳过 undefined / 空串，并按键排序保证依赖稳定。 */
function serializeParams(params?: Record<string, string | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params)
    .filter((entry): entry is [string, string] => entry[1] !== undefined && entry[1] !== "")
    .sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) return "";
  const search = new URLSearchParams();
  for (const [key, value] of entries) search.set(key, value);
  return search.toString();
}
