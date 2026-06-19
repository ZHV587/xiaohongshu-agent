import { useState, useEffect } from "react";
import { SlidersHorizontal, Loader2, Check, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";

export function FeishuConfigPage({ onClose }: { onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [configs, setConfigs] = useState<any>({
    FEISHU_APP_ID: "",
    FEISHU_APP_SECRET: "",
    FEISHU_BITABLE_APP_TOKEN: "",
    FEISHU_BITABLE_TABLE_ID: "",
  });

  useEffect(() => {
    setLoading(true);
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
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
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
    <div className="flex flex-col h-full w-full bg-white p-6 overflow-y-auto text-left">
      <div className="flex justify-between items-center border-b pb-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-charcoal flex items-center gap-2">
            <SlidersHorizontal className="size-5 text-coral animate-pulse" />
            飞书同步与多维表格配置
          </h2>
          <p className="text-xs text-gray-400 mt-1">配置飞书开放平台应用凭证与同步存放小红书文案的多维表格参数</p>
        </div>
        <Button variant="outline" size="sm" onClick={onClose} className="text-xs flex items-center gap-1">
          <ArrowLeft className="size-3" /> 返回会话
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4 py-8">
          <div className="h-4 bg-gray-100 rounded animate-pulse w-1/3" />
          <div className="h-10 bg-gray-100 rounded animate-pulse w-full" />
        </div>
      ) : (
        <form onSubmit={handleSave} className="space-y-6 max-w-2xl">
          <div className="space-y-4">
            <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">飞书自建应用资质</h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-id" className="text-xs font-medium text-gray-500">App ID</Label>
                <Input
                  id="app-id"
                  type="text"
                  value={configs.FEISHU_APP_ID || ""}
                  onChange={(e) => setConfigs({ ...configs, FEISHU_APP_ID: e.target.value })}
                  placeholder="cli_xxx"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-secret" className="text-xs font-medium text-gray-500">App Secret</Label>
                <PasswordInput
                  id="app-secret"
                  value={configs.FEISHU_APP_SECRET || ""}
                  onChange={(e) => setConfigs({ ...configs, FEISHU_APP_SECRET: e.target.value })}
                  placeholder="••••••••••••••••"
                  required
                />
              </div>
            </div>
            <p className="text-[10px] text-gray-400">请确保在飞书开放平台后台授予该应用“云文档 ➔ 多维表格”的读取和写入权限。</p>
          </div>

          <div className="space-y-4 pt-4">
            <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">爆款库多维表格坐标</h3>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="bitable-app-token" className="text-xs font-medium text-gray-500">Bitable App Token</Label>
                <Input
                  id="bitable-app-token"
                  type="text"
                  value={configs.FEISHU_BITABLE_APP_TOKEN || ""}
                  onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_APP_TOKEN: e.target.value })}
                  placeholder="bascnxxxxxxxxxxxx"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bitable-table-id" className="text-xs font-medium text-gray-500">Bitable Table ID (数据表 ID)</Label>
                <Input
                  id="bitable-table-id"
                  type="text"
                  value={configs.FEISHU_BITABLE_TABLE_ID || ""}
                  onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_TABLE_ID: e.target.value })}
                  placeholder="tblxxxxxxxxx"
                  required
                />
              </div>
            </div>
            <p className="text-[10px] text-gray-400">App Token 位于表格 URL 中 `base/` 后面的一长串字符，Table ID 对应具体数据表的子 ID。</p>
          </div>

          <div className="flex items-center justify-end gap-2 border-t pt-4 mt-6">
            <Button
              type="submit"
              disabled={saving}
              className="bg-coral hover:bg-coral-hover active:scale-95 disabled:opacity-50 text-white px-5 py-2 text-sm font-medium rounded-xl flex items-center gap-1.5 shadow-md shadow-coral/10 transition-all cursor-pointer border-none"
            >
              {saving && <Loader2 className="size-4 animate-spin" />}
              {saving ? "保存中..." : "保存配置"}
            </Button>
          </div>
        </form>
      )}

      {showToast && (
        <div className="fixed bottom-6 right-6 bg-emerald-600 text-white px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-300 z-50">
          <Check className="size-4 text-white" />
          <span>飞书配置热更新成功，即时生效。</span>
        </div>
      )}
    </div>
  );
}
