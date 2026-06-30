// PhonePreview — the 小红书 mobile simulator (detail + feed modes).
function PhonePreview({ note, mode, imgIdx, onPrev, onNext }) {
  const { PhoneFrame, NoteCard, IconButton, Avatar } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 24, background: "color-mix(in srgb, var(--oats-default) 60%, white)", display: "flex", justifyContent: "center", alignItems: "flex-start" }} className="custom-scrollbar">
      <PhoneFrame width={330}>
        {mode === "detail" ? (
          <>
            {/* nav */}
            <div style={{ paddingTop: 32, paddingBottom: 12, paddingLeft: 16, paddingRight: 16, borderBottom: "1px solid var(--gray-100)", display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.95)", flexShrink: 0 }}>
              <Icon name="chevron-left" size={20} color="var(--charcoal-default)" />
              <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)" }}>笔记详情</span>
              <Icon name="share" size={16} color="var(--charcoal-default)" />
            </div>

            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }} className="custom-scrollbar">
              {/* carousel */}
              <div style={{ width: "100%", aspectRatio: "1 / 1", position: "relative", overflow: "hidden", flexShrink: 0, background: "var(--accent-surface)" }}>
                <img src={D.images[imgIdx]} alt="cover" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                <div style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}>
                  <IconButton variant="surface" rounded="full" size="sm" label="上一张" onClick={onPrev}><Icon name="chevron-left" size={15} /></IconButton>
                </div>
                <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)" }}>
                  <IconButton variant="surface" rounded="full" size="sm" label="下一张" onClick={onNext}><Icon name="chevron-right" size={15} /></IconButton>
                </div>
                <div style={{ position: "absolute", bottom: 12, left: "50%", transform: "translateX(-50%)", display: "flex", gap: 6 }}>
                  {D.images.map((_, i) => (
                    <span key={i} style={{ width: 6, height: 6, borderRadius: "999px", background: i === imgIdx ? "#fff" : "rgba(255,255,255,0.55)" }} />
                  ))}
                </div>
              </div>

              {/* author */}
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--gray-100)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Avatar name="Z" variant="neutral" size={28} />
                  <div>
                    <div style={{ fontSize: 11, fontWeight: "var(--weight-bold)" }}>{D.user.name}</div>
                    <div style={{ fontSize: 9, color: "var(--text-subtle)" }}>刚才关联了多维表格第 4 行</div>
                  </div>
                </div>
                <button style={{ border: "1px solid var(--primary)", color: "var(--primary)", background: "transparent", padding: "2px 12px", borderRadius: "999px", fontSize: 10, fontWeight: "var(--weight-semibold)", cursor: "pointer" }}>关注</button>
              </div>

              {/* copy */}
              <div style={{ padding: 16, flex: 1 }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)", lineHeight: "var(--leading-snug)" }}>{note.title}</h3>
                <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--charcoal-light)", lineHeight: "var(--leading-relaxed)", whiteSpace: "pre-wrap" }}>{note.body}</p>
              </div>
            </div>

            {/* comment bar */}
            <div style={{ height: 48, borderTop: "1px solid var(--gray-100)", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", background: "#fff", flexShrink: 0, color: "var(--text-muted)" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10 }}><Icon name="heart" size={16} /> 点赞</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10 }}><Icon name="star" size={16} /> 收藏</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10 }}><Icon name="message-square" size={16} /> 评论</span>
            </div>
          </>
        ) : (
          <>
            {/* feed header */}
            <div style={{ paddingTop: 32, paddingBottom: 12, display: "flex", alignItems: "center", justifyContent: "center", gap: 16, background: "rgba(255,255,255,0.97)", borderBottom: "1px solid var(--gray-100)", flexShrink: 0, fontSize: "var(--text-xs)" }}>
              <span style={{ color: "var(--text-subtle)" }}>关注</span>
              <span style={{ fontWeight: "var(--weight-bold)", borderBottom: "2px solid var(--primary)", paddingBottom: 4 }}>发现</span>
              <span style={{ color: "var(--text-subtle)" }}>附近</span>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, alignContent: "start", background: "var(--oats-dark)" }} className="custom-scrollbar">
              <NoteCard image={D.images[imgIdx]} title={note.title} author="张潇潇" authorInitial="Z" likes="1.2k" />
              <NoteCard dim ratio="4 / 5" />
              <NoteCard dim ratio="1 / 1" />
              <NoteCard dim ratio="3 / 4" />
              <NoteCard dim ratio="4 / 5" />
              <NoteCard dim ratio="3 / 4" />
            </div>
          </>
        )}
      </PhoneFrame>
    </div>
  );
}

Object.assign(window, { PhonePreview });
