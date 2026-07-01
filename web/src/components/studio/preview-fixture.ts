// DEV-ONLY visual-verification fixture. Mirrors design_system/ui_kits/studio/
// data.js so /studio-preview can render the studio 1:1 against the prototype
// WITHOUT the backend. NOT shipped: only the /studio-preview route imports it,
// and that route is removed before production (like /ds-gallery). The real
// product (/) gets all of this from the live stream + /api/backend/*.

import type {
  Account,
  CalendarDay,
  DashboardStat,
  EvidenceBundle,
  LibraryItem,
  MonthInfo,
  PublishItem,
  StudioUser,
  Teardown,
  Topic,
  Trend,
} from "./types";

export const FX_USER: StudioUser = { name: "张潇潇", team: "运营组", initial: "Z", handle: "@潇潇的露营笔记", fans: "2.4w" };

export const FX_IMAGES = [
  "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1523987355523-c7b5b0dd90a7?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1510312305653-8ed496efae75?auto=format&fit=crop&w=600&q=80",
];

export const FX_TOPICS: Topic[] = [
  {
    id: 1,
    title: "精致露营「搬家式」装备清单",
    rationale: "视觉冲击 · 高分享率 · 赞藏比极高",
    hotRate: 96,
    angle: "种草清单",
    kw: "露营装备",
    emotional: "把山野过成向往的生活",
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
    id: 2,
    title: "百元搞定！新手露营避坑极简装备",
    rationale: "强实用 · 痛点防坑 · 收藏导向",
    hotRate: 92,
    angle: "避坑干货",
    kw: "新手露营",
    emotional: "第一次露营也能很从容",
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
    id: 3,
    title: "山野落日下的星空篝火美学",
    rationale: "视觉种草 · 情绪共鸣 · 高吸睛",
    hotRate: 88,
    angle: "氛围情绪",
    kw: "露营氛围感",
    emotional: "在山野落日里把日子过成诗",
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
];

export const FX_DASHBOARD: DashboardStat[] = [
  { label: "点赞", value: "1.2k", delta: 18, tone: "coral", icon: "heart" },
  { label: "收藏", value: "864", delta: 32, tone: "success", icon: "star" },
  { label: "评论", value: "207", delta: -4, tone: "neutral", icon: "message-square" },
  { label: "新增粉丝", value: "312", unit: "人", delta: 26, tone: "topic", icon: "user-plus" },
];

export const FX_LIBRARY: LibraryItem[] = [
  { id: 1, title: "精致露营搬家式装备清单", angle: "种草清单", hot: 96, likes: "3.2w", saves: "1.8w", status: "已发布" },
  { id: 2, title: "新手露营避坑极简装备", angle: "避坑干货", hot: 92, likes: "2.1w", saves: "2.4w", status: "排期中" },
  { id: 3, title: "山野落日星空篝火美学", angle: "氛围情绪", hot: 88, likes: "1.5w", saves: "6.2k", status: "草稿" },
  { id: 4, title: "露营咖啡仪式感 3 件套", angle: "好物种草", hot: 85, likes: "9.8k", saves: "7.1k", status: "草稿" },
];

export const FX_TEARDOWN: Teardown = {
  title: "精致露营搬家式装备清单",
  points: [
    { label: "标题", detail: "「精致」+「搬家式」身份标签 + 痛点暗示，搜索词「露营装备」前置" },
    { label: "封面", detail: "暖色实拍大全景 + 4 字大字报，信息密度高" },
    { label: "结构", detail: "共情钩子 → 编号清单 → 选购 TIPS → 互动收口" },
    { label: "标签", detail: "大词(露营) + 中词(精致露营) + 长尾(搬家式露营) 矩阵" },
  ],
};

export const FX_MONTH: MonthInfo = { label: "2026 年 6 月", days: 30, firstOffset: 0 };

export const FX_CALENDAR: CalendarDay[] = [
  { date: 4, items: [{ t: "露营避坑装备", time: "19:30", tone: "coral", acct: "露" }] },
  { date: 6, items: [{ t: "咖啡仪式感", time: "12:00", tone: "topic", acct: "咖" }] },
  { date: 11, items: [{ t: "轻熟风穿搭", time: "20:00", tone: "draft", acct: "穿" }] },
  { date: 14, items: [{ t: "落日篝火美学", time: "18:00", tone: "coral", acct: "露" }, { t: "山野炉饭", time: "21:00", tone: "draft", acct: "食" }] },
  { date: 18, items: [{ t: "防晒装备测评", time: "19:00", tone: "coral", acct: "露" }] },
  { date: 22, items: [{ t: "公园露营 vlog", time: "20:30", tone: "topic", acct: "露" }] },
  { date: 25, items: [{ t: "一人露营", time: "19:00", tone: "draft", acct: "露" }] },
];

export const FX_TRENDS: Trend[] = [
  { tag: "防晒装备", rising: 210, heat: "爆", note: "季节性 · 夏季峰值", tone: "hot" },
  { tag: "公园露营", rising: 132, heat: "高", note: "城市近郊 · 低门槛", tone: "coral" },
  { tag: "露营咖啡", rising: 88, heat: "中", note: "仪式感 · 出片", tone: "topic" },
  { tag: "一人露营", rising: 64, heat: "中", note: "孤独经济 · 上升", tone: "topic" },
];

export const FX_PUBLISH_QUEUE: PublishItem[] = [
  { id: 1, title: "新手露营避坑极简清单", acct: "露", stage: "scheduled", time: "周二 19:30" },
  { id: 2, title: "露营咖啡仪式感 3 件套", acct: "咖", stage: "published", link: "xhslink.com/a/8Kd2", time: "06-26 已发" },
  { id: 3, title: "精致露营搬家式装备清单", acct: "露", stage: "measured", link: "xhslink.com/a/3Fa9", time: "06-20 已回填" },
];

export const FX_ACCOUNTS: Account[] = [
  { id: "camp", handle: "@潇潇的露营笔记", niche: "露营 / 户外", initial: "露", fans: "2.4w", fansNum: 24000, dFans: 312, posts: 12, hot: 91, status: "主力", tone: "coral" },
  { id: "outfit", handle: "@轻熟风穿搭笔记", niche: "穿搭 / 时尚", initial: "穿", fans: "1.9w", fansNum: 19000, dFans: 540, posts: 15, hot: 88, status: "主力", tone: "coral" },
  { id: "coffee", handle: "@潇潇的咖啡日记", niche: "咖啡 / 探店", initial: "咖", fans: "8,600", fansNum: 8600, dFans: 120, posts: 8, hot: 84, status: "成长", tone: "topic" },
  { id: "food", handle: "@山野食验室", niche: "露营美食", initial: "食", fans: "4,200", fansNum: 4200, dFans: 88, posts: 6, hot: 79, status: "孵化", tone: "draft" },
];

export const FX_EVIDENCE: Record<number, EvidenceBundle> = {
  1: {
    mode: "semantic",
    items: [
      { resource_id: "res_note_0421", type: "爆款笔记", title: "搬家式露营装备清单（多维表格 第 4 行）", summary: "赞 3.2w · 藏 1.8w，赞藏比 0.56；「天幕 / 蛋卷桌 / 氛围灯」为高频单品。", score: 0.9132, relevance: 0.94, freshness: 0.82, performance: 0.88, source_updated_at: "2026-06-20", indexed_at: "2026-06-21", why_selected: "与「露营装备」语义最相关，且历史赞藏表现位列类目前 5%。" },
      { resource_id: "res_perf_2207", type: "效果指标", title: "露营类目 · 近 30 天表现基线", summary: "收藏导向内容互动率高于类目均值 38%，清单体裁转发占比最高。", score: 0.7841, relevance: 0.71, freshness: 0.96, performance: 0.8, source_updated_at: "2026-06-27", indexed_at: "2026-06-27", why_selected: "提供时效性最强的类目表现基线，支撑「清单 + 收藏导向」判断。" },
      { resource_id: "res_wiki_0098", type: "选品库 · Wiki", title: "露营选品笔记 · 天幕 / 蛋卷桌 / 氛围灯", summary: "各单品卖点与价格带，飞书 Wiki 接入沉淀。", score: 0.6627, relevance: 0.69, freshness: 0.74, performance: 0.55, source_updated_at: "2026-05-30", indexed_at: "2026-06-02", why_selected: "补全清单单品的卖点细节，图谱 measured_by 关联爆款笔记。" },
    ],
  },
  2: {
    mode: "semantic",
    items: [
      { resource_id: "res_note_0377", type: "爆款笔记", title: "新手露营避坑（藏 2.4w）", summary: "收藏 > 点赞，强收藏导向；平价平替清单结构。", score: 0.8714, relevance: 0.9, freshness: 0.78, performance: 0.84, source_updated_at: "2026-06-18", indexed_at: "2026-06-19", why_selected: "避坑 + 平替结构的高收藏样本，命中「新手露营」语义。" },
      { resource_id: "res_fb_0142", type: "用户反馈", title: "上条避坑笔记评论高频词", summary: "「求清单」「跟着买」高频，价格敏感。", score: 0.7012, relevance: 0.74, freshness: 0.88, performance: 0.61, source_updated_at: "2026-06-22", indexed_at: "2026-06-22", why_selected: "反馈资源（feedback_on 边）佐证价格敏感与清单诉求。" },
    ],
  },
  3: {
    mode: "keyword_fallback",
    items: [
      { resource_id: "res_note_0290", type: "爆款笔记", title: "落日篝火氛围感笔记", summary: "情绪向图文，点赞高、收藏中等；语义相关度偏低，关键词兜底命中。", score: 0.5933, relevance: 0.58, freshness: 0.7, performance: 0.66, source_updated_at: "2026-06-12", indexed_at: "2026-06-14", why_selected: "语义检索未达阈值，按「露营氛围感」关键词兜底召回。" },
    ],
  },
};
