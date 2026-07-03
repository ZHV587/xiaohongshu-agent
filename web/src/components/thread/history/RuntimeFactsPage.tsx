"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, ArrowLeft, CheckCircle2, Clock3, Database, RefreshCw, Server } from "lucide-react";
import { Button, IconButton } from "@/components/ds";
import { runtimeFactRows, type RuntimeFactsPayload, type RuntimeModule } from "./runtime-facts-format";

const MODULES = [
  { key: "startup", label: "启动", icon: Server },
  { key: "scheduler", label: "调度", icon: Activity },
  { key: "database", label: "数据", icon: Database },
];

const STATUS_CLASS: Record<string, string> = {
  healthy: "bg-emerald-50 text-emerald-700 border-emerald-200",
  running: "bg-emerald-50 text-emerald-700 border-emerald-200",
  degraded: "bg-amber-50 text-amber-700 border-amber-200",
  unavailable: "bg-rose-50 text-rose-700 border-rose-200",
  stopped: "bg-gray-100 text-gray-600 border-gray-200",
};

function statusClass(status?: string): string {
  return STATUS_CLASS[status || ""] || "bg-gray-100 text-gray-600 border-gray-200";
}

function RuntimeModuleSection({ label, module, icon: Icon }: { label: string; module?: RuntimeModule; icon: typeof Server }) {
  const rows = module ? runtimeFactRows(module) : [];
  const status = module?.status || "unavailable";

  return (
    <section className="border-border/60 bg-white/70 overflow-hidden rounded-lg border">
      <div className="border-border/50 flex items-center justify-between border-b px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="text-coral size-4 shrink-0" />
          <h3 className="text-charcoal truncate text-sm font-bold">{label}</h3>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClass(status)}`}>
            {status}
          </span>
        </div>
        <span className="text-charcoal-light truncate text-[11px]">{module?.source || "unknown"}</span>
      </div>
      <div className="grid gap-3 px-4 py-3">
        <div className="text-charcoal-light flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
          <span className="flex items-center gap-1">
            <Clock3 className="size-3" />
            {module?.observed_at || "-"}
          </span>
          <span>{module?.stale_after_seconds ? `${module.stale_after_seconds}s` : "-"}</span>
        </div>

        {module?.error && (
          <div className="border-amber-200 bg-amber-50 text-amber-800 flex items-start gap-2 rounded-md border px-3 py-2 text-xs">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <div className="min-w-0">
              <div className="font-semibold">{module.error.code || "RUNTIME_FACT_ERROR"}</div>
              <div className="truncate">{module.error.summary || "Runtime fact unavailable"}</div>
            </div>
          </div>
        )}

        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {rows.length === 0 ? (
            <div className="text-charcoal-light text-xs">暂无可展示指标</div>
          ) : (
            rows.map(([key, value]) => (
              <div key={key} className="bg-oats-light/60 border-border/30 min-w-0 rounded-md border px-3 py-2">
                <dt className="text-charcoal-light truncate text-[10px]">{key}</dt>
                <dd className="text-charcoal mt-0.5 truncate font-mono text-xs tabular-nums">{value}</dd>
              </div>
            ))
          )}
        </dl>
      </div>
    </section>
  );
}

export function RuntimeFactsPage({ onClose }: { onClose: () => void }) {
  const [payload, setPayload] = useState<RuntimeFactsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const response = await fetch("/api/backend/runtime-facts", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error || "Runtime facts unavailable");
      setPayload(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message || "Runtime facts unavailable");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <div className="bg-oats flex h-full w-full flex-col overflow-y-auto p-6 text-left">
      <div className="border-border/80 mb-5 flex items-center justify-between gap-3 border-b pb-4">
        <div className="min-w-0">
          <h2 className="text-charcoal flex items-center gap-2 text-lg font-bold">
            <Activity className="text-coral size-5" />
            运行事实
          </h2>
          <p className="text-charcoal-light mt-1 truncate text-xs">{payload?.observed_at || "等待采样"}</p>
        </div>
        <div className="flex items-center gap-2">
          <IconButton
            label="刷新"
            variant="surface"
            onClick={() => void load(true)}
            disabled={refreshing}
          >
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} />
          </IconButton>
          <Button variant="secondary" size="sm" onClick={onClose} leftIcon={<ArrowLeft className="size-3" />}>
            返回会话
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3">
          {MODULES.map((item) => (
            <div key={item.key} className="bg-white/60 border-border/40 h-32 animate-pulse rounded-lg border" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3">
          {error && (
            <div className="border-rose-200 bg-rose-50 text-rose-700 flex items-center gap-2 rounded-lg border px-4 py-3 text-sm">
              <AlertTriangle className="size-4" />
              {error}
            </div>
          )}
          {payload?.ok && (
            <div className="border-emerald-200 bg-emerald-50 text-emerald-700 flex w-fit items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold">
              <CheckCircle2 className="size-3.5" />
              ok
            </div>
          )}
          {MODULES.map((item) => (
            <RuntimeModuleSection
              key={item.key}
              label={item.label}
              icon={item.icon}
              module={payload?.modules?.[item.key]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
