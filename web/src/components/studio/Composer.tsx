"use client";

// 创作栏可复用子组件。CopyDoctor / ScheduleBar / RiskPanel / EmptyComposer /
// VisualStudio 均绑定真实 Studio 状态与 actions,供深度创作工作台复用。

import { useState } from "react";
import Image from "next/image";
import { Badge, Button, Card, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/useStudio";
import { type CheckResult } from "@/components/studio/rubric";
import { IMAGE_ROLES, type StudioNote } from "@/components/studio/types";

export function EmptyComposer() {
  const { actions, topics, note, progressLabel } = useStudio();
  // 流进行中(status==="writing")但草稿尚未解析出来时,不再显示"还没有草稿 + 生成草稿"
  // (点了也只会提示忙碌),而是显示**动态进度**:主行跟着思考链当前步骤走(真实工具调用派生),
  // 让空态与忙碌态可区分、且有"在动"的感觉,而非一句写死的静态文案。
  const writing = note.status === "writing";
  if (writing) {
    return (
      <Card padding="lg" tone="sunken" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Icon name="loader" size={16} color="var(--primary)" />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-base)", fontWeight: 800, color: "var(--text-body)", display: "flex", alignItems: "center", gap: 6 }}>
            🍠 {progressLabel ? `正在${progressLabel}…` : "正在生成草稿…"}
            <span className="typing-dots" aria-hidden style={{ fontWeight: 800, color: "var(--primary)" }} />
          </div>
          <p style={{ margin: "5px 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>
            智能体正基于数据底座起稿，正文会实时出现在下方创作栏。
          </p>
        </div>
      </Card>
    );
  }
  return (
    <Card padding="lg" tone="sunken" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: "var(--text-base)", fontWeight: 800, color: "var(--text-body)" }}>还没有可编辑草稿</div>
        <p style={{ margin: "5px 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>
          先选择一个选题，或让对话基于真实数据底座起稿；生成后这里会进入完整创作栏。
        </p>
      </div>
      <Button
        variant="primary"
        size="sm"
        leftIcon={<Icon name="sparkles" size={13} />}
        onClick={() => actions.say(topics.length ? "基于当前选题生成一版完整小红书文案" : "先基于数据底座生成 3 个小红书选题")}
      >
        {topics.length ? "生成草稿" : "生成选题"}
      </Button>
    </Card>
  );
}

export function VisualStudio() {
  const { note, images, actions } = useStudio();
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <Eyebrow>视觉工作台 · 封面 + 图集 · 3:4（1080×1440）</Eyebrow>
          <span style={{ fontSize: 9, color: "var(--text-subtle)", whiteSpace: "nowrap" }}>不生成假图，仅使用真实素材</span>
        </div>
        {images.length === 0 ? (
          <Card padding="md" tone="sunken" style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)", lineHeight: "var(--leading-relaxed)" }}>
            暂无图片素材。上传图片或等待数据源返回素材后，封面/图集会在这里预览。
          </Card>
        ) : (
          <div className="cs" style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
            {IMAGE_ROLES.map((role, i) => {
              const cover = i === 0;
              return (
                <div key={role} style={{ width: 148, flexShrink: 0, display: "flex", flexDirection: "column", gap: 5 }}>
                  <div style={{ position: "relative", width: 148, aspectRatio: "3 / 4", borderRadius: "var(--radius-md)", overflow: "hidden", border: cover ? "2px solid var(--primary)" : "1px solid var(--border)", background: "var(--accent-surface)" }}>
                    <Image src={images[i % images.length]} alt={role} fill sizes="148px" unoptimized style={{ objectFit: "cover" }} />
                    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0.42))" }} />
                    {cover && (
                      <textarea
                        value={note.cover}
                        onChange={(e) => actions.updateField("cover", e.target.value)}
                        rows={3}
                        placeholder="封面大字报..."
                        style={{ position: "absolute", top: 10, left: 10, right: 10, border: "none", background: "transparent", resize: "none", color: "#fff", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 17, lineHeight: 1.15, textShadow: "0 2px 6px rgba(0,0,0,0.55)", outline: "none" }}
                      />
                    )}
                    <span style={{ position: "absolute", bottom: 7, left: 7, fontSize: 8, fontWeight: 700, color: cover ? "var(--primary)" : "#fff", background: cover ? "#fff" : "rgba(0,0,0,0.34)", padding: "1px 6px", borderRadius: 999 }}>{cover ? "封面" : role}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

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

// 定稿 → 排期 bar。remaining=未通过的体检项数(可选):60-79 分时做「临界引导」,
// 告诉用户"就差 N 项达标就能定稿",把注意力引到差的那几项而不是干看分数。
export function ScheduleBar({ score, status, remaining }: { score: number; status: StudioNote["status"]; remaining?: number }) {
  const { month, note, selectedAccount, copyLifecycleStatus, setSection, actions } = useStudio();
  const [picking, setPicking] = useState(false);
  const ready = score >= 80;
  const nearReady = !ready && score >= 60;
  const scheduled = status === "scheduled";
  const exactVersion = note.versions?.[note.activeVersion]?.resourceVersion;
  const traceable = Boolean(note.resourceId && exactVersion && copyLifecycleStatus === "ready");
  const schedulingReady = ready && traceable && Boolean(selectedAccount);

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
          <span style={{ fontSize: 11, color: nearReady ? "var(--primary)" : "var(--text-subtle)", fontWeight: nearReady ? 700 : 400, flex: 1 }}>
            {ready
              ? !note.resourceId
                ? "这篇旧稿没有后端资源标识，不能安全排期"
                : !exactVersion
                  ? "当前草稿缺少精确版本号，不能用其他版本代替排期"
                  : copyLifecycleStatus !== "ready"
                    ? "正在确认文案版本状态…"
                    : !selectedAccount
                      ? "体检已达标，请先选择发布账号"
                      : "体检达标，可以定稿啦 🎉"
              : nearReady && remaining
                ? `就差 ${remaining} 项达标就能定稿,再改改这几项 →`
                : `体检 ${score} 分，建议 ≥80 再发`}
          </span>
          <Button variant="secondary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={actions.syncFeishu}>
            同步飞书
          </Button>
          <Button variant="primary" size="sm" leftIcon={<Icon name="calendar-check" size={13} />} onClick={() => setPicking(true)} disabled={!schedulingReady}>
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
