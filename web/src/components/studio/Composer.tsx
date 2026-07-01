"use client";

// 创作栏可复用子组件。保留活跃、被外部 import 的三个组件:
//   CopyDoctor(文案体检)、ScheduleBar(定稿排期)、RiskPanel(限流风控)
// —— 被 DeepEditor / DeepCreation 消费。
// 主编辑器 Composer / EmptyComposer / VisualStudio 已随未挂载路径删除(死代码)。

import { useState } from "react";
import { Badge, Button, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/StudioContext";
import { type CheckResult } from "@/components/studio/rubric";
import { type StudioNote } from "@/components/studio/types";

// 文案体检 scorecard — grouped, driven by the extensible rule library
export function CopyDoctor({ checks, score }: { checks: CheckResult[]; score: number }) {
  const store = useStudio();
  const groups: { name: string; items: CheckResult[] }[] = [];
  checks.forEach((c) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) {
      g = { name: c.group, items: [] };
      groups.push(g);
    }
    g.items.push(c);
  });
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <Icon name="stethoscope" size={15} color="var(--primary)" />
          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>小红书文案体检</span>
          <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>· {checks.length} 项规则</span>
        </div>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: score >= 80 ? "var(--success)" : score >= 60 ? "var(--warning)" : "var(--text-muted)" }}>
          {score}
          <span style={{ fontSize: 11, color: "var(--text-subtle)", fontWeight: 400 }}> 分</span>
        </span>
      </div>
      <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 9, maxHeight: 240, overflowY: "auto" }}>
        {groups.map((g) => {
          const ok = g.items.filter((i) => i.pass).length;
          return (
            <div key={g.name} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <Eyebrow>{g.name}</Eyebrow>
                <span style={{ fontSize: 9, color: ok === g.items.length ? "var(--success)" : "var(--text-subtle)", fontWeight: 600 }}>
                  {ok}/{g.items.length}
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {g.items.map((c) => (
                  <div
                    key={c.key}
                    title={c.hint}
                    style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "5px 8px", borderRadius: "var(--radius-sm)", background: c.pass ? "var(--success-surface)" : "var(--warning-surface)", transition: "background var(--dur-base) var(--ease-out)" }}
                  >
                    <Icon name={c.pass ? "check-circle-2" : "alert-circle"} size={13} color={c.pass ? "var(--success)" : "var(--warning)"} />
                    <span style={{ color: "var(--text-body)", fontWeight: 500, whiteSpace: "nowrap" }}>{c.label}</span>
                    <span style={{ marginLeft: "auto", color: "var(--text-subtle)", fontSize: 10, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 66 }}>{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <button
        onClick={() => store?.actions?.toast?.("规则库可持续扩展：在 data.js 的 checkRules 里增删规则即可（已内置 12 项）")}
        style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontSize: 10, fontWeight: 600, padding: 0 }}
      >
        <Icon name="settings-2" size={12} /> 管理体检规则库
      </button>
    </div>
  );
}

// 定稿 → 排期 bar
export function ScheduleBar({ score, status }: { score: number; status: StudioNote["status"] }) {
  const { month, setSection, actions } = useStudio();
  const [picking, setPicking] = useState(false);
  const ready = score >= 80;
  const scheduled = status === "scheduled";

  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8, position: "sticky", bottom: 0, background: "var(--surface-card)" }}>
      {scheduled ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Badge tone="synced" dot>
            已定稿并排期
          </Badge>
          <Button variant="ghost" size="sm" leftIcon={<Icon name="line-chart" size={13} />} onClick={() => setSection("ops")}>
            去运营看排期
          </Button>
        </div>
      ) : picking ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>排期到 {month.label} 哪天发布？</div>
          <div className="cs" style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, maxHeight: 140, overflowY: "auto" }}>
            {Array.from({ length: month.days }, (_, i) => i + 1).map((d) => (
              <button
                key={d}
                onClick={() => {
                  actions.schedule(d);
                  setPicking(false);
                }}
                style={{ padding: "6px 0", borderRadius: "var(--radius-xs)", border: "1px solid var(--border)", background: "var(--oats-light)", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "var(--text-body)" }}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text-subtle)", flex: 1 }}>{ready ? "体检达标，可以定稿啦 🎉" : `体检 ${score} 分，建议 ≥80 再发`}</span>
          <Button variant="secondary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={actions.syncFeishu}>
            同步飞书
          </Button>
          <Button variant="primary" size="sm" leftIcon={<Icon name="calendar-check" size={13} />} onClick={() => setPicking(true)} disabled={!ready}>
            定稿并排期
          </Button>
        </div>
      )}
    </div>
  );
}

// 限流风控(真实正则检测:导流/极限词/敏感品类)。
// 注:原「原创度 %」曾是硬编码假值(生产恒 72%,无真实来源),已移除——无真实查重/相似度
// 数据源前不展示编造指标(真实数据铁律)。待接入真实原创度检测后再恢复该指标。
export function RiskPanel({ note }: { note: StudioNote }) {
  const text = (note.title || "") + (note.body || "");
  const risks: { label: string; bad: boolean; hint: string }[] = [
    { label: "导流/外链", bad: /http|www\.|公众号|微信|加我|私信|vx|v信|留链|主页链接/i.test(text), hint: "小红书限制站外导流" },
    { label: "极限词", bad: /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久/.test(text), hint: "广告法违禁词" },
    { label: "敏感品类", bad: /医美|减肥|瘦身|药效|代购|烟|酒精/.test(text), hint: "需报备 / 可能限流" },
  ];
  const riskCount = risks.filter((r) => r.bad).length;
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <Icon name="shield-check" size={15} color="var(--primary)" />
          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>限流风控</span>
        </div>
        <span style={{ fontSize: 10, color: riskCount ? "var(--warning)" : "var(--success)", fontWeight: 600 }}>{riskCount ? `${riskCount} 项风险` : "无明显风险"}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {risks.map((r) => (
          <div key={r.label} title={r.hint} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, padding: "5px 7px", borderRadius: "var(--radius-sm)", background: r.bad ? "var(--warning-surface)" : "var(--success-surface)" }}>
            <Icon name={r.bad ? "alert-triangle" : "check-circle-2"} size={12} color={r.bad ? "var(--warning)" : "var(--success)"} />
            <span style={{ fontWeight: 500 }}>{r.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
