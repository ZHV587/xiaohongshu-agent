// App — root of the 小红书文案助手 workbench recreation.
function App() {
  const D = window.XHS_DATA;
  const [activeRecent, setActiveRecent] = React.useState(1);
  const [note, setNote] = React.useState(D.topics[0]);
  const [chosenId, setChosenId] = React.useState(null);
  const [writing, setWriting] = React.useState(false);
  const [tab, setTab] = React.useState("mock");
  const [mode, setMode] = React.useState("detail");
  const [imgIdx, setImgIdx] = React.useState(0);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [scanned, setScanned] = React.useState(false);
  const [input, setInput] = React.useState("");

  // Ctrl+P / Esc
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const selectTopic = (id) => {
    const topic = D.topics.find((t) => t.id === id);
    setChosenId(id);
    setWriting(true);
    setTab("mock");
    setMode("detail");
    setTimeout(() => {
      setNote(topic);
      setImgIdx(0);
      setWriting(false);
    }, 1500);
  };

  const runCommand = (cmd) => {
    setPaletteOpen(false);
    setNote((n) => {
      if (cmd === "polish") {
        return { ...n, body: "⛺ 夏日避暑天花板！露营党看过来！✨\n\n" + n.body };
      }
      if (cmd === "shorten") {
        return { ...n, body: n.body.slice(0, 300).trimEnd() + "…\n\n#露营必备 #户外美学" };
      }
      if (cmd === "tags") {
        return { ...n, body: n.body.trimEnd() + " #夏日避暑指南 #爆款露营装备" };
      }
      return n;
    });
  };

  const nextImg = () => setImgIdx((i) => (i + 1) % D.images.length);
  const prevImg = () => setImgIdx((i) => (i - 1 + D.images.length) % D.images.length);

  return (
    <div style={{ height: "100vh", width: "100vw", display: "flex", flexDirection: "column", overflow: "hidden", color: "var(--text-body)", fontFamily: "var(--font-sans)" }}>
      <TopBar onReauth={() => { setTab("feishu"); setScanned(false); }} />
      <main style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Sidebar activeId={activeRecent} onSelect={setActiveRecent} onNewChat={() => { setChosenId(null); setWriting(false); }} />
        <ChatPane
          chosenId={chosenId}
          writing={writing}
          onSelectTopic={selectTopic}
          onOpenPalette={() => setPaletteOpen(true)}
          input={input}
          setInput={setInput}
          onSend={() => { if (input.trim()) { setInput(""); } }}
        />
        <RightCanvas
          note={note}
          tab={tab} setTab={setTab}
          mode={mode} setMode={setMode}
          imgIdx={imgIdx} onPrev={prevImg} onNext={nextImg}
          scanned={scanned} onScan={() => setScanned(true)}
        />
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onRun={runCommand} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
