"use client";

// TEMPORARY verification gallery for the ported ds/* components.
// Used to pixel-compare against design_system/components/*.card.html.
// Deleted after Phase 1 sign-off.

import {
  Avatar,
  Badge,
  Button,
  Card,
  HashtagTag,
  IconButton,
  Icon,
  Input,
  NoteCard,
  PhoneFrame,
  Select,
  StatCard,
  Textarea,
  ThinkingAura,
  TopicCard,
} from "@/components/ds";

function Row({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--text-subtle)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)" }}>{title}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>{children}</div>
    </div>
  );
}

export default function DsGallery() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--background)", padding: 40, color: "var(--text-body)", fontFamily: "var(--font-sans)" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", flexDirection: "column", gap: 32 }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-2xl)", letterSpacing: "var(--tracking-tight)" }}>
          🍠 Design System · ds/* 保真验证
        </h1>

        <Row title="Buttons">
          <Button variant="primary">生成</Button>
          <Button variant="secondary">次要</Button>
          <Button variant="soft">软按钮</Button>
          <Button variant="ghost">幽灵</Button>
          <Button variant="primary" loading>生成中</Button>
          <Button variant="primary" leftIcon={<Icon name="send" size={15} />}>立即同步至飞书</Button>
        </Row>

        <Row title="IconButtons">
          <IconButton variant="ghost" label="ghost"><Icon name="log-out" size={18} /></IconButton>
          <IconButton variant="soft" label="soft"><Icon name="share" size={18} /></IconButton>
          <IconButton variant="solid" label="solid"><Icon name="plus" size={18} /></IconButton>
          <IconButton variant="surface" label="surface"><Icon name="chevron-left" size={18} /></IconButton>
        </Row>

        <Row title="Badges">
          <Badge tone="neutral">Ready</Badge>
          <Badge tone="synced" dot>已同步</Badge>
          <Badge tone="hot">爆款</Badge>
          <Badge tone="topic">数据</Badge>
          <Badge tone="info">config</Badge>
          <Badge tone="coral">coral</Badge>
          <Badge tone="draft" shape="chip">草稿</Badge>
        </Row>

        <Row title="Avatars">
          <Avatar name="Zhang Wei" />
          <Avatar variant="solid" name="Li" />
          <Avatar variant="neutral" name="Wu" />
          <Avatar variant="agent" glyph="🍠" size={36} />
        </Row>

        <Row title="HashtagTags">
          <HashtagTag>精致露营</HashtagTag>
          <HashtagTag tone="coral">爆款露营装备</HashtagTag>
          <HashtagTag tone="plain">户外好物</HashtagTag>
          <HashtagTag addable onAdd={() => {}}>夏日避暑指南</HashtagTag>
        </Row>

        <Row title="Cards">
          <Card style={{ width: 240 }}>普通卡片 · 白面 oats 画布</Card>
          <Card tone="sunken" style={{ width: 240 }}>sunken 卡片</Card>
          <Card interactive style={{ width: 240 }}>可点击卡片(hover 上浮变珊瑚)</Card>
        </Row>

        <Row title="Forms">
          <Input placeholder="搜索资料库…" leadingIcon={<Icon name="search" size={15} />} containerStyle={{ width: 260 }} />
          <Select options={["选项一", "选项二", "选项三"]} containerStyle={{ width: 180 }} />
          <Textarea placeholder="在此输入小红书正文…" containerStyle={{ width: 320 }} footer={<span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }}>540 / 1000 字</span>} />
        </Row>

        <Row title="TopicCard / ThinkingAura">
          <div style={{ width: 360 }}>
            <TopicCard index={1} title="夏日露营装备清单" rationale="切中季节痛点，装备类目转化高" hotRate={96} onClick={() => {}} />
          </div>
          <div style={{ width: 360 }}>
            <ThinkingAura
              steps={[
                { label: "已连接飞书多维表格 (45 条数据)", state: "done" },
                { label: "正在计算博主点赞权重并提炼选题规律…", state: "active" },
                { label: "撰写小红书原生文案", state: "pending" },
              ]}
              logs={[{ time: "12:03", text: "解析爆款库字段映射" }, { time: "12:04", text: "提炼出 3 个选题方向" }]}
            />
          </div>
        </Row>

        <Row title="StatCard (含 editable 数据回填)">
          <div style={{ width: 180 }}><StatCard label="粉丝总数" value="12.4k" delta={8} icon={<Icon name="users" size={15} />} tone="coral" /></div>
          <div style={{ width: 180 }}><StatCard label="爆款率" value="96" unit="%" delta={-3} tone="success" /></div>
          <div style={{ width: 180 }}><StatCard label="近7天点赞" value="3204" editable onValueChange={() => {}} /></div>
        </Row>

        <Row title="Device — PhoneFrame & NoteCard">
          <PhoneFrame width={220}>
            <div style={{ paddingTop: 30, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ aspectRatio: "3/4", borderRadius: 12, background: "var(--accent-surface)" }} />
              <div style={{ fontWeight: 700, fontSize: "var(--text-sm)" }}>⛺ 夏日避暑天花板！</div>
            </div>
          </PhoneFrame>
          <div style={{ width: 150 }}><NoteCard title="⛺ 夏日避暑天花板，露营党看过来" author="露营菌" authorInitial="露" likes="2.3k" /></div>
          <div style={{ width: 150 }}><NoteCard dim /></div>
        </Row>
      </div>
    </div>
  );
}
