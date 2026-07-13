"use client";

import { Badge } from "@/components/ds";
import type { UserSkillSummary } from "./types";

export function SkillStatus({ status }: { status: UserSkillSummary["status"] }) {
  const labels = { draft: "草稿", published: "已发布", disabled: "已停用", archived: "已归档" };
  return (
    <Badge tone={status === "published" ? "synced" : status === "draft" ? "draft" : "neutral"} shape="chip">
      {labels[status]}
    </Badge>
  );
}
