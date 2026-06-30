// ChatPane — the center conversation column + composer.
function ChatPane({ chosenId, writing, onSelectTopic, onOpenPalette, input, setInput, onSend }) {
  const { Card, Avatar, Button, Textarea, TopicCard, ThinkingAura } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const scrollRef = React.useRef(null);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chosenId, writing]);

  const chosen = D.topics.find((t) => t.id === chosenId);

  return (
    <section style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--background)", minWidth: 0 }}>
      <div ref={scrollRef} className="custom-scrollbar" style={{ flex: 1, overflowY: "auto", padding: 24, display: "flex", flexDirection: "column", gap: 22 }}>

        {/* User prompt */}
        <Bubble side="user">帮我按露营装备方向出选题，并从飞书多维表格中筛选高赞的爆款。</Bubble>

        {/* Agent: thinking + topics */}
        <div style={{ display: "flex", gap: 12, maxWidth: "88%" }}>
          <Avatar glyph="🍠" variant="agent" />
          <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
            <div style={{ width: 460, maxWidth: "100%" }}>
              <ThinkingAura steps={D.thinkingSteps} logs={D.thinkingLogs} />
            </div>
            <Card padding="md" style={{ borderColor: "var(--border-coral)" }}>
              <p style={{ margin: "0 0 12px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)" }}>
                分析了飞书多维表格中互动量前 10% 的露营装备相关笔记，我提炼出以下 3 个高爆款概率的选题方向。点击卡片即可让我撰写正文：
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {D.topics.map((t) => (
                  <TopicCard key={t.id} index={t.id} title={t.title} rationale={t.rationale} hotRate={t.hotRate} onClick={() => onSelectTopic(t.id)} />
                ))}
              </div>
            </Card>
          </div>
        </div>

        {/* User reaction */}
        {chosen && <Bubble side="user">写第 {chosen.id} 个选题。</Bubble>}

        {/* Agent writing status */}
        {writing && (
          <div style={{ display: "flex", gap: 12, maxWidth: "88%" }}>
            <Avatar glyph="🍠" variant="agent" />
            <div style={{ display: "inline-flex", alignItems: "center", gap: 10, background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "12px 16px", fontSize: "var(--text-sm)", color: "var(--text-muted)", boxShadow: "var(--shadow-sm)" }}>
              <span style={{ width: 16, height: 16, borderRadius: "999px", border: "2px solid var(--primary)", borderTopColor: "transparent", animation: "spin 0.7s linear infinite" }} />
              正在针对《{chosen?.title}》撰写小红书风格文案，并流式同步至右侧预览…
            </div>
          </div>
        )}

        {/* Agent done */}
        {chosen && !writing && (
          <div style={{ display: "flex", gap: 12, maxWidth: "88%" }}>
            <Avatar glyph="🍠" variant="agent" />
            <Card padding="md">
              <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)" }}>
                ✅ 已完成《{chosen.title}》的正文撰写，右侧手机预览已更新。可继续微调，或切到「飞书同步协作」一键写入多维表格。
              </p>
            </Card>
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{ padding: 24, borderTop: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ maxWidth: "var(--composer-max)", margin: "0 auto" }}>
          <Textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="说说你想写什么方向，或按 Ctrl+P 调起润色工具箱..."
            footer={<>
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <button onClick={onOpenPalette} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer", fontFamily: "var(--font-sans)" }}>
                  <kbd style={{ fontSize: 8, background: "var(--oats-light)", border: "1px solid var(--border)", padding: "1px 4px", borderRadius: 4, fontFamily: "var(--font-mono)" }}>Ctrl+P</kbd>
                  <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>润色工具箱</span>
                </button>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                  <Icon name="plus" size={15} /> 图片或 PDF
                </span>
              </div>
              <Button variant="primary" size="sm" rightIcon={<Icon name="send" size={14} />} onClick={onSend}>生成</Button>
            </>}
          />
        </div>
      </div>
    </section>
  );
}

function Bubble({ side, children }) {
  const { Avatar } = window.DesignSystem_71831b;
  const isUser = side === "user";
  return (
    <div style={{ display: "flex", gap: 12, maxWidth: "85%", alignSelf: isUser ? "flex-end" : "flex-start", flexDirection: isUser ? "row-reverse" : "row" }}>
      {isUser ? <Avatar name="我" variant="solid" size={32} /> : <Avatar glyph="🍠" variant="agent" />}
      <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "12px 16px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", boxShadow: "var(--shadow-sm)" }}>
        {children}
      </div>
    </div>
  );
}

Object.assign(window, { ChatPane });
