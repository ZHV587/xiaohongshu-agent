import { useState, useEffect, type ReactNode } from "react";
import { SlidersHorizontal, Loader2, Check, ArrowLeft, BookOpen, KeyRound, Info } from "lucide-react";
import { Button, Input } from "@/components/ds";

function FieldLabel({ htmlFor, children, className = "" }: { htmlFor?: string; children: ReactNode; className?: string }) {
  return (
    <label htmlFor={htmlFor} className={`text-xs font-medium text-charcoal-light ${className}`}>
      {children}
    </label>
  );
}

export function FeishuConfigPage({ onClose }: { onClose: () => void }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [configs, setConfigs] = useState<any>({
    FEISHU_APP_ID: "",
    FEISHU_APP_SECRET: "",
    FEISHU_BITABLE_APP_TOKEN: "",
    FEISHU_BITABLE_TABLE_ID: "",
    FEISHU_BITABLE_COLLECT_TABLE_ID: "",
    FEISHU_WIKI_SPACE_ID: "",
  });
  const [wikiSpaceName, setWikiSpaceName] = useState("小红书爆单手册");

  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok && data.configs) {
          // Keep all existing config values but only control/render the Feishu related ones.
          setConfigs(data.configs);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));

    fetch("/api/feishu/wiki-space")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.name) {
          setWikiSpaceName(data.name);
        }
      })
      .catch(console.error);
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!configs.FEISHU_APP_ID || !configs.FEISHU_APP_SECRET) {
      alert("请输入 App ID 和 App Secret");
      return;
    }

    setSaving(true);
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configs }),
      });
      if (res.ok) {
        setShowToast(true);
        setTimeout(() => {
          setShowToast(false);
          onClose();
        }, 1500);
      } else {
        alert("保存配置失败，请检查输入项");
      }
    } catch (err) {
      console.error(err);
      alert("网络请求异常");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-oats p-6 overflow-y-auto text-left custom-scrollbar">
      <div className="flex justify-between items-center border-b border-border/80 pb-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-charcoal flex items-center gap-2">
            <SlidersHorizontal className="size-5 text-coral animate-pulse" />
            飞书同步与多维表格配置
          </h2>
          <p className="text-xs text-charcoal-light mt-1">配置飞书开放平台应用凭证与同步存放小红书文案的多维表格参数</p>
        </div>
        <Button variant="secondary" size="sm" onClick={onClose} leftIcon={<ArrowLeft className="size-3" />}>
          返回会话
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4 py-8">
          <div className="h-6 bg-oats-dark rounded animate-pulse w-1/4" />
          <div className="h-20 bg-oats-dark rounded animate-pulse w-full" />
          <div className="h-20 bg-oats-dark rounded animate-pulse w-full" />
        </div>
      ) : (
        <form onSubmit={handleSave} className="w-full max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] xl:grid-cols-[1fr_400px] gap-8 items-start">
            {/* 左侧：表单配置 */}
            <div className="space-y-6 bg-white/40 p-5 rounded-2xl border border-border/30 backdrop-blur-xs">
              <div className="space-y-4">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">飞书自建应用资质</h3>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="app-id">App ID</FieldLabel>
                    <Input
                      id="app-id"
                      type="text"
                      value={configs.FEISHU_APP_ID || ""}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_APP_ID: e.target.value })}
                      placeholder="cli_xxx"
                      required
                      className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="app-secret">App Secret</FieldLabel>
                    <Input
                      id="app-secret"
                      type="password"
                      value={configs.FEISHU_APP_SECRET || ""}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_APP_SECRET: e.target.value })}
                      placeholder="••••••••••••••••"
                      required
                      className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-gray-400">请确保在飞书开放平台后台授予该应用“云文档 ➔ 多维表格”与“云文档 ➔ 知识库”的读取与写入相关权限。</p>
              </div>

              <div className="space-y-4 pt-4">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">爆款库多维表格坐标</h3>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="bitable-app-token">Bitable App Token</FieldLabel>
                    <Input
                      id="bitable-app-token"
                      type="text"
                      value={configs.FEISHU_BITABLE_APP_TOKEN || ""}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_APP_TOKEN: e.target.value })}
                      placeholder="bascnxxxxxxxxxxxx"
                      className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="bitable-table-id">Bitable Table ID (草稿/选题主表)</FieldLabel>
                    <Input
                      id="bitable-table-id"
                      type="text"
                      value={configs.FEISHU_BITABLE_TABLE_ID || ""}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_TABLE_ID: e.target.value })}
                      placeholder="tblxxxxxxxxx"
                      className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="bitable-collect-table-id">爆款采集库 Table ID (线上笔记采纳写入)</FieldLabel>
                    <Input
                      id="bitable-collect-table-id"
                      type="text"
                      value={configs.FEISHU_BITABLE_COLLECT_TABLE_ID || ""}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_COLLECT_TABLE_ID: e.target.value })}
                      placeholder="tbl24vSVeLvz45ig"
                      className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-gray-400">App Token 位于表格 URL 中 `base/` 后面的一长串字符，Table ID 对应具体数据表的子 ID。采集库表 ID 独立于草稿表，用于线上笔记“采纳收录”的镜像写入(默认 tbl24vSVeLvz45ig)。</p>
              </div>

              <div className="space-y-4 pt-4 border-t border-border/30">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">飞书知识库 (Wiki) 绑定</h3>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <FieldLabel className="flex items-center gap-1.5">
                      <span>知识空间 ({wikiSpaceName})</span>
                      <span className="bg-oats text-coral text-[9px] px-1.5 py-0.5 rounded font-normal">后端写死绑定</span>
                    </FieldLabel>
                    <div className="bg-oats-light/20 border border-border/30 px-3 py-2 rounded-lg text-xs text-charcoal font-mono select-all flex justify-between items-center">
                      <span>7648177996175543260</span>
                      <a
                        href="https://ycnaxi4z2bte.feishu.cn/wiki/settings/7648177996175543260"
                        target="_blank"
                        rel="noreferrer"
                        className="text-[10px] text-coral hover:underline font-semibold"
                      >
                        在飞书打开 ↗
                      </a>
                    </div>
                  </div>
                </div>
                <p className="text-[10px] text-gray-400">按照您的要求，该知识空间已在后端直接绑定，以确保特定操作始终引用您指定的参考资料库。</p>
              </div>

              <div className="flex items-center justify-end gap-2 border-t border-border/80 pt-4 mt-6">
                <Button
                  type="submit"
                  disabled={saving}
                  className="bg-coral hover:bg-coral-hover text-white active:scale-95 disabled:opacity-50 px-6 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-1.5 shadow-md shadow-coral/10 transition-all cursor-pointer border-none"
                >
                  {saving && <Loader2 className="size-4 animate-spin" />}
                  {saving ? "正在应用..." : "应用飞书配置"}
                </Button>
              </div>
            </div>

            {/* 右侧：飞书指南与向导 */}
            <div className="hidden lg:flex flex-col gap-6 sticky top-0">
              {/* 参数寻找步骤 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-4 shadow-sm text-xs">
                <h3 className="font-bold text-charcoal flex items-center gap-1.5 border-b pb-2">
                  <BookOpen className="size-4 text-coral" />
                  如何定位表格与知识库参数？
                </h3>
                <div className="space-y-3 text-charcoal-light leading-relaxed">
                  <div>
                    <span className="font-semibold text-charcoal block mb-0.5">1. Bitable App Token (应用凭证)</span>
                    <p className="text-[11px]">
                      打开您的飞书多维表格，在浏览器的地址栏中，URL 路径里紧随 <code className="bg-oats/60 px-1 py-0.5 rounded text-[10px]">/base/</code> 后面的一长串乱码字符即为 App Token。
                    </p>
                    <span className="text-[10px] text-gray-400 block mt-0.5 font-mono">
                      https://.../base/<span className="text-coral underline font-bold">bascnXXXXXXXXXXXXXX</span>?table=...
                    </span>
                  </div>
                  <div>
                    <span className="font-semibold text-charcoal block mb-0.5">2. Bitable Table ID (数据表子 ID)</span>
                    <p className="text-[11px]">
                      在多维表格页面底部切换工作表时，浏览器地址栏中 <code className="bg-oats/60 px-1 py-0.5 rounded text-[10px]">table=</code> 参数后面的值，即为当前数据表的子 ID。
                    </p>
                    <span className="text-[10px] text-gray-400 block mt-0.5 font-mono">
                      https://.../base/...?table=<span className="text-coral underline font-bold">tblXXXXXXXXX</span>&view=...
                    </span>
                  </div>
                </div>
              </div>

              {/* 自建应用授权清单 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-3.5 shadow-sm text-xs">
                <h3 className="font-bold text-charcoal flex items-center gap-1.5 border-b pb-2">
                  <KeyRound className="size-4 text-coral" />
                  飞书自建应用必要权限
                </h3>
                <p className="text-charcoal-light leading-relaxed">
                  为了使智能体正常工作（同步文案、读取爆款与参考知识库等），请在飞书后台开通以下权限并发布版本：
                </p>
                <div className="grid grid-cols-1 gap-1.5 font-mono text-[10px]">
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>bitable:app (表格读写)</span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>wiki:space:read (知识空间只读)</span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>wiki:node:read (知识节点只读)</span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>wiki:node:retrieve (获取节点列表)</span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>docx:document:readonly (文档块只读)</span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-oats-light/40 border border-border/30 px-2.5 py-1.5 rounded-lg text-charcoal">
                    <Check className="size-3.5 text-emerald-500 shrink-0" />
                    <span>im:message (发送消息)</span>
                  </div>
                </div>
              </div>

              {/* 提示信息 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-2 shadow-sm text-[10px] text-charcoal-light flex items-start gap-2">
                <Info className="size-4 text-coral shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-charcoal block mb-0.5">请记得在飞书平台“发布版本”</span>
                  自建应用在修改任何权限范围 (Scope) 后，必须在“版本管理与发布”中创建一个新版本并申请上线。若状态为“已上线”，权限修改才会真正对 API 调用生效。
                </div>
              </div>
            </div>
          </div>
        </form>
      )}

      {showToast && (
        <div className="fixed bottom-6 right-6 bg-charcoal text-white px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-300 z-50 border border-border/10">
          <Check className="size-4 text-emerald-400" />
          <span>飞书同步配置更新成功，已即时热重载生效！</span>
        </div>
      )}
    </div>
  );
}
