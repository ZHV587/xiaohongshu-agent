// Content for the 小红书创作运营工作室 (Studio) prototype.
window.STUDIO = {
  user: { name: "张潇潇", team: "运营组", initial: "Z", handle: "@潇潇的露营笔记", fans: "2.4w" },

  images: [
    "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1523987355523-c7b5b0dd90a7?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1510312305653-8ed496efae75?auto=format&fit=crop&w=600&q=80",
  ],

  recents: [
    { id: 1, icon: "⛺", title: "露营装备好物推荐", status: "synced" },
    { id: 2, icon: "☕", title: "咖啡探店爆款草稿", status: "draft" },
    { id: 3, icon: "👗", title: "夏季轻熟风穿搭笔记", status: "draft" },
  ],

  // Viral topic suggestions. Each carries a full version-A draft so a
  // click can stream a real note into the composer.
  topics: [
    {
      id: 1, title: "精致露营「搬家式」装备清单", rationale: "视觉冲击 · 高分享率 · 赞藏比极高", hotRate: 96, angle: "种草清单", kw: "露营装备", emotional: "把山野过成向往的生活",
      draft: {
        title: "精致露营搬家式装备清单｜少带一件都后悔",
        cover: "搬家式露营\n必带清单",
        body: `夏天太适合露营啦！⛺ 作为一个精致的搬家式露营玩家，带什么装备真的大有讲究！今天把我私藏的露营装备好物全分享给你们，少带一件体验感都打折！

👇 精致露营必带清单：
1️⃣ 双顶充气天幕：防雨防晒，拍照超出片，8 人也宽敞
2️⃣ 蛋卷桌 + 月亮椅：精致露营的灵魂，放上咖啡机格调拉满
3️⃣ 氛围串灯 / 汽灯：天黑挂起暖黄灯串，氛围感封神 ✨
4️⃣ 便携制冰机：山野里来一口冰冷萃，这就是向往的生活

📝 挑选 TIPS：买前先看折叠收纳体积！我后备箱就是这么满的（笑哭）

你还有什么露营神器？评论区一起交流呀～`,
        tags: ["精致露营", "露营清单", "户外好物", "露营装备", "周末去哪儿", "搬家式露营"],
      },
    },
    {
      id: 2, title: "百元搞定！新手露营避坑极简装备", rationale: "强实用 · 痛点防坑 · 收藏导向", hotRate: 92, angle: "避坑干货", kw: "新手露营", emotional: "第一次露营也能很从容",
      draft: {
        title: "百元搞定！新手露营避坑极简清单",
        cover: "新手露营\n避坑清单",
        body: `别被大几千的装备劝退！新手第一次露营，主打性价比和实用 ✅ 今天教你用几百块搞定一整套，少花冤枉钱！

❌ 千万别买的雷区：
- 百元以下简易帐篷：防雨差、一吹就倒
- 巨重实木蛋卷桌：搬一次就想扔

✅ 闭眼入平替清单：
1️⃣ 自动速开帐篷（￥200）：省心省力不满头汗
2️⃣ 铝合金桌 + 月亮椅（￥150）：轻便好带、坐着舒服
3️⃣ 防风卡式炉（￥50）：煮面烧水性价比天花板

觉得有用赶紧收藏，露营时翻出来对着买！`,
        tags: ["新手露营", "露营避坑", "性价比", "露营装备", "省钱攻略"],
      },
    },
    {
      id: 3, title: "山野落日下的星空篝火美学", rationale: "视觉种草 · 情绪共鸣 · 高吸睛", hotRate: 88, angle: "氛围情绪", kw: "露营氛围感", emotional: "在山野落日里把日子过成诗",
      draft: {
        title: "山野落日 + 星空篝火，氛围感封神 🌅",
        cover: "落日篝火\n氛围感",
        body: `当太阳缓缓落进山头，把整片山野染成蜜橘色的那一刻，我就知道这趟露营值了。🌅

夜幕降临，串灯亮起，篝火噼啪作响，朋友围坐聊到深夜——这种慢下来的露营氛围感，才是真正的奢侈。✨

📷 出片小心机：
1️⃣ 落日逆光拍剪影，氛围拉满
2️⃣ 串灯绕在天幕支架，夜景随手出片
3️⃣ 篝火 + 热饮特写，温暖治愈

愿你也能在山野里，找到属于自己的星空。点赞收藏，下次照着拍 🌿`,
        tags: ["露营氛围感", "星空露营", "落日", "治愈系", "露营拍照"],
      },
    },
  ],

  recommendedTags: ["新手必看", "露营好物", "氛围感", "夏日露营", "搬家式露营", "露营避坑指南", "周末去哪儿", "出片攻略"],
  quickEmoji: ["🍠", "⛺", "☕", "✨", "🌿", "👇", "📝", "🔥", "🌅", "✅", "❌", "1️⃣", "2️⃣", "💛"],

  // ── 账号运营 ──
  dashboard: [
    { label: "点赞", value: "1.2k", delta: 18, tone: "coral", icon: "heart" },
    { label: "收藏", value: "864", delta: 32, tone: "success", icon: "star" },
    { label: "评论", value: "207", delta: -4, tone: "neutral", icon: "message-square" },
    { label: "新增粉丝", value: "312", unit: "人", delta: 26, tone: "topic", icon: "user-plus" },
  ],

  library: [
    { id: 1, title: "精致露营搬家式装备清单", angle: "种草清单", hot: 96, likes: "3.2w", saves: "1.8w", status: "已发布" },
    { id: 2, title: "新手露营避坑极简装备", angle: "避坑干货", hot: 92, likes: "2.1w", saves: "2.4w", status: "排期中" },
    { id: 3, title: "山野落日星空篝火美学", angle: "氛围情绪", hot: 88, likes: "1.5w", saves: "6.2k", status: "草稿" },
    { id: 4, title: "露营咖啡仪式感 3 件套", angle: "好物种草", hot: 85, likes: "9.8k", saves: "7.1k", status: "草稿" },
  ],
  teardown: {
    title: "精致露营搬家式装备清单",
    points: [
      { label: "标题", detail: "「精致」+「搬家式」身份标签 + 痛点暗示，搜索词「露营装备」前置" },
      { label: "封面", detail: "暖色实拍大全景 + 4 字大字报，信息密度高" },
      { label: "结构", detail: "共情钩子 → 编号清单 → 选购 TIPS → 互动收口" },
      { label: "标签", detail: "大词(露营) + 中词(精致露营) + 长尾(搬家式露营) 矩阵" },
    ],
  },

  weekdays: ["一", "二", "三", "四", "五", "六", "日"],
  month: { label: "2026 年 6 月", days: 30, firstOffset: 0 },
  calendar: [
    { date: 4, items: [{ t: "露营避坑装备", time: "19:30", tone: "coral", acct: "露" }] },
    { date: 6, items: [{ t: "咖啡仪式感", time: "12:00", tone: "topic", acct: "咖" }] },
    { date: 11, items: [{ t: "轻熟风穿搭", time: "20:00", tone: "draft", acct: "穿" }] },
    { date: 14, items: [{ t: "落日篝火美学", time: "18:00", tone: "coral", acct: "露" }, { t: "山野炉饭", time: "21:00", tone: "draft", acct: "食" }] },
    { date: 18, items: [{ t: "防晒装备测评", time: "19:00", tone: "coral", acct: "露" }] },
    { date: 22, items: [{ t: "公园露营 vlog", time: "20:30", tone: "topic", acct: "露" }] },
    { date: 25, items: [{ t: "一人露营", time: "19:00", tone: "draft", acct: "露" }] },
  ],
};

// 热点趋势雷达（外部实时信号，区别于内部历史沉淀；探索 exploration 的输入）
window.STUDIO.trends = [
  { tag: "防晒装备", rising: 210, heat: "爆", note: "季节性 · 夏季峰值", tone: "hot" },
  { tag: "公园露营", rising: 132, heat: "高", note: "城市近郊 · 低门槛", tone: "coral" },
  { tag: "露营咖啡", rising: 88, heat: "中", note: "仪式感 · 出片", tone: "topic" },
  { tag: "一人露营", rising: 64, heat: "中", note: "孤独经济 · 上升", tone: "topic" },
];

// 图集角色（小红书是图文：封面权重 > 正文）
window.STUDIO.imageRoles = ["封面 · 大字报", "产品特写", "场景氛围", "清单合影", "选购对比"];

// 发布 → 回链 → 回填 状态机（打通效果闭环最后一公里；小红书无开放发布 API）
window.STUDIO.publishQueue = [
  { id: 1, title: "新手露营避坑极简清单", acct: "露", stage: "scheduled", time: "周二 19:30" },
  { id: 2, title: "露营咖啡仪式感 3 件套", acct: "咖", stage: "published", link: "xhslink.com/a/8Kd2", time: "06-26 已发" },
  { id: 3, title: "精致露营搬家式装备清单", acct: "露", stage: "measured", link: "xhslink.com/a/3Fa9", time: "06-20 已回填" },
];

// 多账号矩阵（账号作为一等公民：各自垂类/人设/粉丝/状态）
window.STUDIO.accounts = [
  { id: "camp", handle: "@潇潇的露营笔记", niche: "露营 / 户外", initial: "露", fans: "2.4w", fansNum: 24000, dFans: 312, posts: 12, hot: 91, status: "主力", tone: "coral" },
  { id: "outfit", handle: "@轻熟风穿搭笔记", niche: "穿搭 / 时尚", initial: "穿", fans: "1.9w", fansNum: 19000, dFans: 540, posts: 15, hot: 88, status: "主力", tone: "coral" },
  { id: "coffee", handle: "@潇潇的咖啡日记", niche: "咖啡 / 探店", initial: "咖", fans: "8,600", fansNum: 8600, dFans: 120, posts: 8, hot: 84, status: "成长", tone: "topic" },
  { id: "food", handle: "@山野食验室", niche: "露营美食", initial: "食", fans: "4,200", fansNum: 4200, dFans: 88, posts: 6, hot: 79, status: "孵化", tone: "draft" },
];

// ── 创作依据（数据底座检索到的资源 + rank_evidence 三信号）──
// 对齐 evidence.py 的 EvidenceItem 契约：source_updated_at vs indexed_at、
// score、why_selected；retrieval_mode ∈ semantic/keyword_fallback/insufficient_relevance。
window.STUDIO.evidence = {
  1: {
    mode: "semantic",
    items: [
      { resource_id: "res_note_0421", type: "爆款笔记", title: "搬家式露营装备清单（多维表格 第 4 行）", summary: "赞 3.2w · 藏 1.8w，赞藏比 0.56；「天幕 / 蛋卷桌 / 氛围灯」为高频单品。", score: 0.9132, relevance: 0.94, freshness: 0.82, performance: 0.88, source_updated_at: "2026-06-20", indexed_at: "2026-06-21", why_selected: "与「露营装备」语义最相关，且历史赞藏表现位列类目前 5%。" },
      { resource_id: "res_perf_2207", type: "效果指标", title: "露营类目 · 近 30 天表现基线", summary: "收藏导向内容互动率高于类目均值 38%，清单体裁转发占比最高。", score: 0.7841, relevance: 0.71, freshness: 0.96, performance: 0.80, source_updated_at: "2026-06-27", indexed_at: "2026-06-27", why_selected: "提供时效性最强的类目表现基线，支撑「清单 + 收藏导向」判断。" },
      { resource_id: "res_wiki_0098", type: "选品库 · Wiki", title: "露营选品笔记 · 天幕 / 蛋卷桌 / 氛围灯", summary: "各单品卖点与价格带，飞书 Wiki 接入沉淀。", score: 0.6627, relevance: 0.69, freshness: 0.74, performance: 0.55, source_updated_at: "2026-05-30", indexed_at: "2026-06-02", why_selected: "补全清单单品的卖点细节，图谱 measured_by 关联爆款笔记。" },
    ],
  },
  2: {
    mode: "semantic",
    items: [
      { resource_id: "res_note_0377", type: "爆款笔记", title: "新手露营避坑（藏 2.4w）", summary: "收藏 > 点赞，强收藏导向；平价平替清单结构。", score: 0.8714, relevance: 0.90, freshness: 0.78, performance: 0.84, source_updated_at: "2026-06-18", indexed_at: "2026-06-19", why_selected: "避坑 + 平替结构的高收藏样本，命中「新手露营」语义。" },
      { resource_id: "res_fb_0142", type: "用户反馈", title: "上条避坑笔记评论高频词", summary: "「求清单」「跟着买」高频，价格敏感。", score: 0.7012, relevance: 0.74, freshness: 0.88, performance: 0.61, source_updated_at: "2026-06-22", indexed_at: "2026-06-22", why_selected: "反馈资源（feedback_on 边）佐证价格敏感与清单诉求。" },
    ],
  },
  3: {
    mode: "keyword_fallback",
    items: [
      { resource_id: "res_note_0290", type: "爆款笔记", title: "落日篝火氛围感笔记", summary: "情绪向图文，点赞高、收藏中等；语义相关度偏低，关键词兜底命中。", score: 0.5933, relevance: 0.58, freshness: 0.70, performance: 0.66, source_updated_at: "2026-06-12", indexed_at: "2026-06-14", why_selected: "语义检索未达阈值，按「露营氛围感」关键词兜底召回。" },
    ],
  },
};


// ── 文案体检规则库（可持续扩充：往这个数组追加规则即可）──
// 每条规则 = { key, group, label, hint, test(note) -> { pass, value } }
(function () {
  const G = /\p{Extended_Pictographic}/gu, ONE = /\p{Extended_Pictographic}/u;
  const banned = /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久|官方认证|最便宜/;
  const benefit = /防雨|防晒|省|平价|搞定|避坑|出片|氛围|必带|轻便|性价比|治愈|宽敞|不踩雷/;
  const first = (n) => (n.body || "").slice(0, 120);
  window.STUDIO.checkRules = [
    { key: "title_len", group: "标题", label: "标题长度", hint: "≤20 字最易读",
      test: (n) => ({ pass: n.title.length > 0 && n.title.length <= 20, value: n.title.length ? `${n.title.length} 字` : "—" }) },
    { key: "title_hook", group: "标题", label: "标题钩子", hint: "数字/痛点/情绪/emoji",
      test: (n) => ({ pass: /[0-9０-９！!?？]|绝了|谁懂|必看|后悔|攻略|清单|避坑|收藏|平替|天花板|宝藏|封神/.test(n.title) || ONE.test(n.title), value: ONE.test(n.title) ? "含 emoji" : (/[0-9]/.test(n.title) ? "含数字" : "—") }) },
    { key: "keyword_front", group: "标题", label: "关键词前置", hint: "核心搜索词进标题+首段",
      test: (n) => { const k = (n.kw || "").slice(0, 2); return { pass: !!k && n.title.includes(k) && first(n).includes(k), value: n.kw || "—" }; } },
    { key: "emoji", group: "正文", label: "Emoji 密度", hint: "每段 1–2 个",
      test: (n) => { const c = (n.body.match(G) || []).length; return { pass: c >= 6, value: `${c} 个` }; } },
    { key: "structure", group: "正文", label: "分点结构", hint: "编号清单 / ✅❌",
      test: (n) => ({ pass: /1️⃣|2️⃣|3️⃣|✅|❌/.test(n.body), value: /1️⃣/.test(n.body) ? "清单" : "—" }) },
    { key: "benefit_front", group: "正文", label: "利益点前置", hint: "前 120 字给到利益/痛点",
      test: (n) => ({ pass: benefit.test(first(n)), value: benefit.test(first(n)) ? "已前置" : "—" }) },
    { key: "interact", group: "正文", label: "互动引导", hint: "求评论/收藏/关注",
      test: (n) => ({ pass: /评论|收藏|关注|点赞|交流|码住|抄作业|蹲一个/.test(n.body), value: /收藏/.test(n.body) ? "已加" : "—" }) },
    { key: "length", group: "正文", label: "字数", hint: "≤1000 字",
      test: (n) => ({ pass: n.body.length > 0 && n.body.length <= 1000, value: `${n.body.length}/1000` }) },
    { key: "tag_count", group: "标签", label: "标签数量", hint: "5–10 个",
      test: (n) => ({ pass: n.tags.length >= 5 && n.tags.length <= 10, value: `${n.tags.length} 个` }) },
    { key: "tag_longtail", group: "标签", label: "长尾标签", hint: "含 ≥4 字长尾词",
      test: (n) => ({ pass: n.tags.some((t) => t.length >= 4), value: n.tags.some((t) => t.length >= 4) ? "已含" : "缺长尾" }) },
    { key: "cover", group: "封面", label: "封面文案", hint: "3–6 字大字报",
      test: (n) => ({ pass: !!n.cover, value: n.cover ? "已设" : "—" }) },
    { key: "compliance", group: "合规", label: "违禁词规避", hint: "无极限词/违禁词",
      test: (n) => ({ pass: !banned.test((n.title || "") + (n.body || "")), value: banned.test((n.title || "") + (n.body || "")) ? "含违禁词" : "无违禁词" }) },
  ];
})();
