// 小红书文案体检 — extensible rule library, faithfully ported from
// 小红书文案助手 Design System/ui_kits/studio/data.js (checkRules) + ui.jsx
// (computeChecks / scoreOf). This is REAL rule logic (regex evaluation),
// not mock business data — it powers the live, instant 文案体检 feedback
// as the user types. The authoritative score is ALSO computed server-side
// by the rubric tool (content_rubric.py) per the plan; this client copy is
// the zero-latency mirror.

export interface NoteDraft {
  title: string;
  body: string;
  tags: string[];
  cover?: string;
  kw?: string;
}

export interface CheckRule {
  key: string;
  group: string;
  label: string;
  hint: string;
  test: (n: NoteDraft) => { pass: boolean; value: string };
}

export interface CheckResult {
  key: string;
  group: string;
  label: string;
  hint: string;
  pass: boolean;
  value: string;
}

const G = /\p{Extended_Pictographic}/gu;
const ONE = /\p{Extended_Pictographic}/u;
const banned = /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久|官方认证|最便宜/;
const benefit = /防雨|防晒|省|平价|搞定|避坑|出片|氛围|必带|轻便|性价比|治愈|宽敞|不踩雷/;
const first = (n: NoteDraft) => (n.body || "").slice(0, 120);

export const CHECK_RULES: CheckRule[] = [
  {
    key: "title_len",
    group: "标题",
    label: "标题长度",
    hint: "≤20 字最易读",
    test: (n) => ({ pass: n.title.length > 0 && n.title.length <= 20, value: n.title.length ? `${n.title.length} 字` : "—" }),
  },
  {
    key: "title_hook",
    group: "标题",
    label: "标题钩子",
    hint: "数字/痛点/情绪/emoji",
    test: (n) => ({
      pass: /[0-9０-９！!?？]|绝了|谁懂|必看|后悔|攻略|清单|避坑|收藏|平替|天花板|宝藏|封神/.test(n.title) || ONE.test(n.title),
      value: ONE.test(n.title) ? "含 emoji" : /[0-9]/.test(n.title) ? "含数字" : "—",
    }),
  },
  {
    key: "keyword_front",
    group: "标题",
    label: "关键词前置",
    hint: "核心搜索词进标题+首段",
    test: (n) => {
      const k = (n.kw || "").slice(0, 2);
      return { pass: !!k && n.title.includes(k) && first(n).includes(k), value: n.kw || "—" };
    },
  },
  {
    key: "emoji",
    group: "正文",
    label: "Emoji 密度",
    hint: "每段 1–2 个",
    test: (n) => {
      const c = (n.body.match(G) || []).length;
      return { pass: c >= 6, value: `${c} 个` };
    },
  },
  {
    key: "structure",
    group: "正文",
    label: "分点结构",
    hint: "编号清单 / ✅❌",
    test: (n) => ({ pass: /1️⃣|2️⃣|3️⃣|✅|❌/.test(n.body), value: /1️⃣/.test(n.body) ? "清单" : "—" }),
  },
  {
    key: "benefit_front",
    group: "正文",
    label: "利益点前置",
    hint: "前 120 字给到利益/痛点",
    test: (n) => ({ pass: benefit.test(first(n)), value: benefit.test(first(n)) ? "已前置" : "—" }),
  },
  {
    key: "interact",
    group: "正文",
    label: "互动引导",
    hint: "求评论/收藏/关注",
    test: (n) => ({ pass: /评论|收藏|关注|点赞|交流|码住|抄作业|蹲一个/.test(n.body), value: /收藏/.test(n.body) ? "已加" : "—" }),
  },
  {
    key: "length",
    group: "正文",
    label: "字数",
    hint: "≤1000 字",
    test: (n) => ({ pass: n.body.length > 0 && n.body.length <= 1000, value: `${n.body.length}/1000` }),
  },
  {
    key: "tag_count",
    group: "标签",
    label: "标签数量",
    hint: "5–10 个",
    test: (n) => ({ pass: n.tags.length >= 5 && n.tags.length <= 10, value: `${n.tags.length} 个` }),
  },
  {
    key: "tag_longtail",
    group: "标签",
    label: "长尾标签",
    hint: "含 ≥4 字长尾词",
    test: (n) => ({ pass: n.tags.some((t) => t.length >= 4), value: n.tags.some((t) => t.length >= 4) ? "已含" : "缺长尾" }),
  },
  {
    key: "cover",
    group: "封面",
    label: "封面文案",
    hint: "3–6 字大字报",
    test: (n) => ({ pass: !!n.cover, value: n.cover ? "已设" : "—" }),
  },
  {
    key: "compliance",
    group: "合规",
    label: "违禁词规避",
    hint: "无极限词/违禁词",
    test: (n) => ({ pass: !banned.test((n.title || "") + (n.body || "")), value: banned.test((n.title || "") + (n.body || "")) ? "含违禁词" : "无违禁词" }),
  },
];

export function computeChecks(note: NoteDraft): CheckResult[] {
  return CHECK_RULES.map((r) => {
    let res: { pass?: boolean; value?: string } = {};
    try {
      res = r.test(note) || {};
    } catch {
      res = {};
    }
    return { key: r.key, group: r.group || "其他", label: r.label, hint: r.hint, pass: !!res.pass, value: res.value || "—" };
  });
}

export const scoreOf = (checks: CheckResult[]): number =>
  checks.length === 0 ? 0 : Math.round((checks.filter((c) => c.pass).length / checks.length) * 100);
