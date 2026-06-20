export type RuntimeModule = {
  status?: string;
  source?: string;
  observed_at?: string;
  stale_after_seconds?: number;
  data?: Record<string, any>;
  error?: {
    code?: string;
    summary?: string;
  };
};

export type RuntimeFactsPayload = {
  ok?: boolean;
  observed_at?: string;
  modules?: Record<string, RuntimeModule>;
};

export type RuntimeFactRow = [string, string];

function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  return "-";
}

function countRows(prefix: string, value: unknown, keys: string[]): RuntimeFactRow[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const record = value as Record<string, unknown>;
  return keys.map((key) => [`${prefix}.${key}`, text(record[key])]);
}

export function runtimeFactRows(module: RuntimeModule): RuntimeFactRow[] {
  const data = module.data || {};
  const rows: RuntimeFactRow[] = [];

  rows.push(...countRows("startup", data, ["instance_id", "started_at", "stopped_at"]));
  rows.push(
    ...countRows("scheduler", data, [
      "instance_id",
      "accepting_work",
      "last_cycle_status",
      "last_cycle_started_at",
      "last_cycle_finished_at",
    ]),
  );

  const outbox = data.outbox;
  if (outbox && typeof outbox === "object" && !Array.isArray(outbox)) {
    for (const key of ["pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded"]) {
      rows.push([key, text((outbox as Record<string, unknown>)[key])]);
    }
  }

  const sources = data.sources;
  if (sources && typeof sources === "object" && !Array.isArray(sources)) {
    for (const key of ["enabled", "expired", "running", "last_status"]) {
      rows.push([`sources.${key}`, text((sources as Record<string, unknown>)[key])]);
    }
  }

  const resources = data.resources;
  if (resources && typeof resources === "object" && !Array.isArray(resources)) {
    rows.push(["resources.total", text((resources as Record<string, unknown>).total)]);
    rows.push(["resources.last_indexed_at", text((resources as Record<string, unknown>).last_indexed_at)]);
  }

  const embedding = data.embedding;
  if (embedding && typeof embedding === "object" && !Array.isArray(embedding)) {
    for (const status of ["active", "building"]) {
      const item = (embedding as Record<string, unknown>)[status];
      if (item && typeof item === "object" && !Array.isArray(item)) {
        const record = item as Record<string, unknown>;
        rows.push([`embedding.${status}.config`, text(record.config_version)]);
        rows.push([`embedding.${status}.progress`, `${text(record.completed_resources)}/${text(record.expected_resources)}`]);
        rows.push([`embedding.${status}.failed`, text(record.failed_resources)]);
      } else {
        rows.push([`embedding.${status}`, "-"]);
      }
    }
  }

  return rows.filter(([, value]) => value !== "-");
}
