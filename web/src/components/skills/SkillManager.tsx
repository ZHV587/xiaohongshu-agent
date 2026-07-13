"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Badge, Button, Icon, Input, Textarea } from "@/components/ds";
import {
  appendUserSkillVersion,
  createUserSkill,
  runUserSkillAction,
  SkillApiError,
  validateUserSkill,
} from "./api";
import { SkillStatus } from "./SkillStatus";
import { useCapabilityRegistry } from "./CapabilityRegistryContext";
import {
  EMPTY_SKILL_DEFINITION,
  type UserSkillDefinition,
  type UserSkillDetail,
  type UserSkillVersion,
} from "./types";

export function SkillManager() {
  const registry = useCapabilityRegistry();
  const { loadSkillDetail } = registry;
  const available = registry.userSkills;
  const [selectedId, setSelectedId] = useState<string | null>(registry.managerSkillId ?? available.find((item) => item.status !== "archived")?.id ?? null);
  const [creating, setCreating] = useState(available.length === 0 && !registry.managerSkillId);
  const [detail, setDetail] = useState<UserSkillDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId || creating) return;
    let alive = true;
    void Promise.resolve().then(async () => {
      if (alive) setLoadingDetail(true);
      try {
        const value = await loadSkillDetail(selectedId, true);
        if (alive) { setDetail(value); setLoadError(null); }
      } catch (error) {
        if (alive) setLoadError(error instanceof Error ? error.message : "能力详情加载失败。");
      } finally {
        if (alive) setLoadingDetail(false);
      }
    });
    return () => { alive = false; };
  }, [creating, loadSkillDetail, selectedId]);

  const select = (id: string) => {
    setDetail(null);
    setLoadError(null);
    setCreating(false);
    setSelectedId(id);
  };
  const onSaved = async (skillId: string) => {
    await registry.refreshSkills();
    setCreating(false);
    setSelectedId(skillId);
    const value = await registry.loadSkillDetail(skillId, true);
    setDetail(value);
  };

  return (
    <div onClick={registry.closeManager} style={{ position: "fixed", inset: 0, zIndex: 125, padding: "4vh 14px", display: "flex", justifyContent: "center", background: "rgba(15,15,16,0.4)" }}>
      <section role="dialog" aria-modal="true" aria-label="管理我的 Skill" onClick={(event) => event.stopPropagation()} style={{ width: "min(1120px, 98vw)", height: "min(820px, 92vh)", display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--background)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-2xl)" }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 17px", borderBottom: "1px solid var(--border)", background: "var(--surface-card)" }}>
          <div>
            <strong style={{ fontSize: "var(--text-sm)" }}>管理我的 Skill</strong>
            <span style={{ marginLeft: 8, fontSize: 10, color: "var(--text-subtle)" }}>草稿不会影响已发布版本，发布后才参与自动路由</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <Button variant="soft" size="sm" leftIcon={<Icon name="plus" size={13} />} onClick={() => { setDetail(null); setLoadError(null); setCreating(true); setSelectedId(null); }}>新建 Skill</Button>
            <Button variant="secondary" size="sm" onClick={registry.openToolbox}>返回工具箱</Button>
            <Button variant="ghost" size="sm" leftIcon={<Icon name="x" size={14} />} onClick={registry.closeManager}>关闭</Button>
          </div>
        </header>

        <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "260px minmax(0, 1fr)" }}>
          <aside style={{ minHeight: 0, padding: 12, borderRight: "1px solid var(--border)", background: "var(--surface-sidebar)", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: "var(--text-subtle)", padding: "4px 7px" }}>我的 Skill · {available.length}</div>
            <div className="cs" style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 5 }}>
              {available.map((skill) => (
                <button key={skill.id} onClick={() => select(skill.id)} style={{ display: "flex", flexDirection: "column", gap: 5, padding: "10px 11px", borderRadius: "var(--radius-md)", border: selectedId === skill.id && !creating ? "1px solid var(--border-coral)" : "1px solid transparent", background: selectedId === skill.id && !creating ? "var(--accent-surface)" : "transparent", textAlign: "left", cursor: "pointer" }}>
                  <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, width: "100%" }}>
                    <strong style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "var(--text-xs)", color: "var(--text-body)" }}>{skill.displayName}</strong>
                    <SkillStatus status={skill.status} />
                  </span>
                  <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>最新 v{skill.latestVersion}{skill.publishedVersion ? ` · 发布 v${skill.publishedVersion}` : ""}</span>
                </button>
              ))}
              {available.length === 0 && <div style={{ padding: 14, fontSize: "var(--text-xs)", color: "var(--text-subtle)", lineHeight: 1.7 }}>还没有 Skill。新建后先校验和试运行，再决定是否发布。</div>}
            </div>
          </aside>

          <main className="cs" style={{ minWidth: 0, overflowY: "auto", padding: 18 }}>
            {loadError && <Message tone="error">{loadError}</Message>}
            {loadingDetail && !creating ? <Message>正在加载能力详情…</Message> : (
              <SkillEditor key={creating ? "new" : detail?.id ?? "empty"} detail={creating ? null : detail} onSaved={onSaved} />
            )}
          </main>
        </div>
      </section>
    </div>
  );
}

export function SkillEditor({ detail, onSaved }: { detail: UserSkillDetail | null; onSaved: (skillId: string) => Promise<void> }) {
  const registry = useCapabilityRegistry();
  const [definition, setDefinition] = useState<UserSkillDefinition>(() => detail?.latest.definition ?? EMPTY_SKILL_DEFINITION);
  const [triggerText, setTriggerText] = useState(() => (detail?.latest.definition.triggerExamples ?? []).join("\n"));
  const [nonTriggerText, setNonTriggerText] = useState(() => (detail?.latest.definition.nonTriggerExamples ?? []).join("\n"));
  const [tagsText, setTagsText] = useState(() => (detail?.latest.definition.tags ?? []).join("、"));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState("");
  const readonly = detail?.status === "archived";
  const hasUnpublishedLatest = !!detail && detail.latestVersion !== detail.publishedVersion;

  const payload = useMemo<UserSkillDefinition>(() => ({
    ...definition,
    triggerExamples: splitLines(triggerText),
    nonTriggerExamples: splitLines(nonTriggerText),
    tags: splitTags(tagsText),
  }), [definition, nonTriggerText, tagsText, triggerText]);

  const perform = async (name: string, action: () => Promise<void>) => {
    setBusy(name); setMessage(null); setFieldErrors({});
    try { await action(); }
    catch (error) {
      if (error instanceof SkillApiError) setFieldErrors(error.fieldErrors);
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "操作失败，请稍后重试。" });
    } finally { setBusy(null); }
  };

  const validate = () => perform("validate", async () => {
    const result = await validateUserSkill(payload);
    setPreview(result.skillMd);
    setMessage({ tone: "ok", text: "校验通过：名称、路由描述和执行说明都符合要求。" });
  });

  const save = () => perform("save", async () => {
    const result = detail
      ? await appendUserSkillVersion(detail.id, detail.latestVersion, payload)
      : await createUserSkill(payload);
    await onSaved(result.skill.id);
    setMessage({ tone: "ok", text: detail ? "已保存为新的不可变版本。" : "草稿已创建。" });
  });

  const lifecycle = (action: "publish" | "enable" | "disable" | "archive", version?: number) => perform(action, async () => {
    if (!detail) return;
    if (action === "archive" && !window.confirm("归档后将不能再编辑或执行，确定归档吗？")) return;
    await runUserSkillAction(detail.id, action, version);
    await onSaved(detail.id);
    setMessage({ tone: "ok", text: action === "publish" ? "已发布，新的对话会自动发现这项能力。" : action === "enable" ? "已重新启用。" : action === "disable" ? "已停用，不再参与自动路由。" : "已归档。" });
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: "var(--text-lg)" }}>{detail ? detail.latest.definition.displayName : "新建 Skill"}</h2>
          <p style={{ margin: "4px 0 0", fontSize: 10, color: "var(--text-subtle)" }}>{detail ? `${detail.runtimeName} · 最新 v${detail.latestVersion}` : "填写通用工作流；不要在说明里申请工具、脚本或额外权限。"}</p>
        </div>
        {detail && <SkillStatus status={detail.status} />}
      </div>

      {message && <Message tone={message.tone}>{message.text}</Message>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="显示名称" error={fieldErrors.displayName} count={`${payload.displayName.length}/80`}>
          <Input value={definition.displayName} invalid={!!fieldErrors.displayName} disabled={readonly} onChange={(event) => setDefinition((value) => ({ ...value, displayName: event.target.value }))} placeholder="例如：事实优先改写" />
        </Field>
        <Field label="标签" error={fieldErrors.tags} hint="用逗号、顿号或换行分隔">
          <Input value={tagsText} invalid={!!fieldErrors.tags} disabled={readonly} onChange={(event) => setTagsText(event.target.value)} placeholder="结构、真人感、职场" />
        </Field>
      </div>

      <Field label="路由描述" error={fieldErrors.description} count={`${payload.description.length}/500`} hint="说明什么情况下应该使用；Agent 主要根据这段话自动路由">
        <Input value={definition.description} invalid={!!fieldErrors.description} disabled={readonly} onChange={(event) => setDefinition((value) => ({ ...value, description: event.target.value }))} placeholder="当用户需要……时使用" />
      </Field>

      <Field label="执行说明" error={fieldErrors.instructions} count={`${payload.instructions.length}/32768`} hint="写清处理步骤、判断标准和输出格式；不用重复常识">
        <Textarea rows={10} value={definition.instructions} invalid={!!fieldErrors.instructions} disabled={readonly} onChange={(event) => setDefinition((value) => ({ ...value, instructions: event.target.value }))} placeholder={"1. 先判断……\n2. 再处理……\n3. 最后按以下格式输出……"} />
      </Field>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="适用示例" error={fieldErrors.triggerExamples} hint="每行一句，帮助自动路由">
          <Textarea rows={4} value={triggerText} invalid={!!fieldErrors.triggerExamples} disabled={readonly} onChange={(event) => setTriggerText(event.target.value)} placeholder={"帮我压缩一下结构\n把这段话说得更直接"} />
        </Field>
        <Field label="不适用示例" error={fieldErrors.nonTriggerExamples} hint="每行一句，减少误触发">
          <Textarea rows={4} value={nonTriggerText} invalid={!!fieldErrors.nonTriggerExamples} disabled={readonly} onChange={(event) => setNonTriggerText(event.target.value)} placeholder={"帮我扩写案例\n只检查错别字"} />
        </Field>
      </div>

      {!readonly && (
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 7, paddingTop: 4 }}>
          <Button variant="secondary" loading={busy === "validate"} onClick={validate} leftIcon={<Icon name="shield-check" size={14} />}>校验</Button>
          <Button loading={busy === "save"} onClick={save} leftIcon={<Icon name="check" size={14} />}>{detail ? "保存新版本" : "创建草稿"}</Button>
          {hasUnpublishedLatest && detail?.status !== "disabled" && <Button variant="soft" onClick={() => void registry.executeUser(detail, "test")}>试运行最新版本</Button>}
          {hasUnpublishedLatest && (detail?.status === "draft" || detail?.status === "published") && <Button variant="secondary" loading={busy === "publish"} onClick={() => lifecycle("publish", detail.latestVersion)}>发布最新版本</Button>}
          {detail?.status === "published" && <Button variant="secondary" loading={busy === "disable"} onClick={() => lifecycle("disable")}>停用</Button>}
          {detail?.status === "disabled" && <Button variant="secondary" loading={busy === "enable"} onClick={() => lifecycle("enable")}>启用</Button>}
          {detail && <Button variant="ghost" loading={busy === "archive"} onClick={() => lifecycle("archive")} style={{ marginLeft: "auto", color: "var(--primary)" }}>归档</Button>}
        </div>
      )}

      {preview && (
        <details>
          <summary style={{ cursor: "pointer", fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--text-muted)" }}>查看校验后的 SKILL.md</summary>
          <pre style={{ maxHeight: 260, overflow: "auto", padding: 12, borderRadius: "var(--radius-md)", background: "var(--charcoal-dark)", color: "white", fontSize: 10, whiteSpace: "pre-wrap" }}>{preview}</pre>
        </details>
      )}

      {detail && <VersionHistory detail={detail} onChanged={() => onSaved(detail.id)} />}
    </div>
  );
}

export function VersionHistory({ detail, onChanged }: { detail: UserSkillDetail; onChanged: () => Promise<void> }) {
  const [busyVersion, setBusyVersion] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const versions = [...detail.versions].sort((a, b) => b.version - a.version);
  const rollback = async (version: UserSkillVersion) => {
    if (!window.confirm(`确定回滚到 v${version.version} 吗？历史版本不会被删除。`)) return;
    setBusyVersion(version.version); setError(null);
    try { await runUserSkillAction(detail.id, "rollback", version.version); await onChanged(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "回滚失败，请稍后重试。"); }
    finally { setBusyVersion(null); }
  };
  return (
    <section style={{ borderTop: "1px solid var(--border)", paddingTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}><Icon name="history" size={14} /><strong style={{ fontSize: "var(--text-sm)" }}>版本历史</strong><Badge tone="draft" shape="chip">{versions.length}</Badge></div>
      {error && <Message tone="error">{error}</Message>}
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {versions.map((version) => {
          const published = detail.publishedVersion === version.version;
          return (
            <div key={version.versionId} style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 10px", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", background: published ? "var(--success-surface)" : "var(--surface-card)" }}>
              <strong style={{ fontSize: "var(--text-xs)" }}>v{version.version}</strong>
              {published && <Badge tone="synced" shape="chip">当前发布</Badge>}
              {detail.latestVersion === version.version && !published && <Badge tone="draft" shape="chip">最新草稿</Badge>}
              <span style={{ flex: 1, fontSize: 10, color: "var(--text-subtle)" }}>{version.definition.displayName} · {formatDate(version.createdAt)}</span>
              {!published && detail.status !== "archived" && detail.publishedVersion != null && version.version < detail.publishedVersion && (
                <Button variant="ghost" size="sm" loading={busyVersion === version.version} onClick={() => rollback(version)}>回滚到此版本</Button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Field({ label, hint, count, error, children }: { label: string; hint?: string; count?: string; error?: string; children: ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>{label}</span>
        <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{count}</span>
      </span>
      {hint && <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{hint}</span>}
      {children}
      {error && <span style={{ fontSize: 10, color: "var(--primary)" }}>{error}</span>}
    </label>
  );
}

function Message({ tone = "normal", children }: { tone?: "normal" | "ok" | "error"; children: ReactNode }) {
  return <div style={{ padding: "9px 11px", borderRadius: "var(--radius-sm)", fontSize: "var(--text-xs)", background: tone === "error" ? "var(--accent-surface)" : tone === "ok" ? "var(--success-surface)" : "var(--oats-light)", color: tone === "error" ? "var(--primary)" : tone === "ok" ? "var(--success)" : "var(--text-muted)" }}>{children}</div>;
}

function splitLines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function splitTags(value: string): string[] {
  return value.split(/[\n,，、]/).map((item) => item.trim()).filter(Boolean);
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", { hour12: false });
}
