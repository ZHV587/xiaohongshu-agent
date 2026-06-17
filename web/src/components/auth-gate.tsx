// 登录门禁:未登录锁住整个应用,只显示中文登录页;登录成功才渲染子内容。
// 放在 ThreadProvider/StreamProvider 之外,确保未登录时不会向后端发任何请求。
"use client";

import { ReactNode, useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, type CurrentUser } from "@/lib/auth";
import { motion, AnimatePresence } from "framer-motion";
import { KeyRound, ShieldAlert, CheckCircle2, QrCode, LogIn } from "lucide-react";
import { AUTH_COOKIE } from "@/lib/server/feishu";

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false); // 客户端挂载后才判定,避免 SSR 闪烁
  const [authError, setAuthError] = useQueryState("auth_error");
  const [isFlipped, setIsFlipped] = useState(false);
  const [scanSuccess, setScanSuccess] = useState(false);

  useEffect(() => {
    setUser(getCurrentUser());
    setReady(true);
  }, []);

  // 飞书登录回调失败时,? auth_error=... 会带回来,在登录页提示后清掉。
  useEffect(() => {
    if (authError) {
      toast.error("登录失败", {
        description: authError,
        richColors: true,
        closeButton: true,
      });
      setAuthError(null);
    }
  }, [authError, setAuthError]);

  // 挂载前不渲染任何东西,避免未登录界面一闪而过。
  if (!ready) return null;

  // 已登录:放行。
  if (user) return <>{children}</>;

  const handleSimulateLogin = () => {
    setScanSuccess(true);
    setTimeout(() => {
      // 写入本地调试 JWT 认证 cookie，模拟飞书登录成功
      document.cookie = `${AUTH_COOKIE}=mock-jwt-token; path=/; max-age=604800`;
      setUser({
        openId: "dev-user",
        name: "本地测试用户 (调试)"
      });
    }, 1200);
  };

  // 未登录:全屏中文登录页,锁住应用。
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-oats p-4 select-none">
      <div className="w-[380px] h-[340px] perspective-1000">
        <motion.div
          className="relative w-full h-full preserve-3d"
          animate={{ rotateY: isFlipped ? 180 : 0 }}
          transition={{ type: "spring", stiffness: 150, damping: 20 }}
          style={{ width: "100%", height: "100%" }}
        >
          {/* 登录卡片正面 */}
          <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-coral-light rounded-2xl shadow-xl p-8 flex flex-col justify-between">
            <div className="flex flex-col items-center text-center gap-3">
              <span className="bg-coral text-white text-3xl size-14 flex items-center justify-center rounded-2xl shadow-md">🍠</span>
              <h2 className="text-xl font-bold tracking-tight text-charcoal font-display">{BRAND.name}</h2>
              <p className="text-xs text-charcoal-light leading-relaxed">
                绑定您的飞书应用与用户身份，解锁多维表格爆款分析、即时协作和自动分发功能。
              </p>
            </div>
            
            <div className="flex flex-col gap-2">
              <Button
                size="lg"
                className="w-full bg-coral hover:bg-coral-hover text-white py-3 px-4 rounded-xl flex items-center justify-center gap-2 font-medium shadow-md transition-all cursor-pointer border-none"
                onClick={() => setIsFlipped(true)}
              >
                <QrCode className="size-4" />
                <span>使用飞书扫码安全登录</span>
              </Button>
            </div>
          </div>

          {/* 登录卡片背面 */}
          <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-coral-light rounded-2xl shadow-xl p-8 flex flex-col justify-between [transform:rotateY(180deg)]">
            <AnimatePresence mode="wait">
              {!scanSuccess ? (
                <motion.div
                  key="scan-view"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-between h-full w-full"
                >
                  <div className="flex items-start gap-2.5 text-left w-full">
                    <ShieldAlert className="size-5 text-coral shrink-0 mt-0.5" />
                    <div className="flex-grow">
                      <h4 className="text-xs font-bold text-coral">飞书授权登录</h4>
                      <p className="text-[9px] text-gray-400 mt-0.5">请使用飞书移动端扫描下方二维码以授予智能体接口协作权限。</p>
                    </div>
                  </div>

                  <div 
                    onClick={handleSimulateLogin}
                    className="relative bg-white p-2.5 border border-coral-light rounded-xl shadow-md cursor-pointer group"
                  >
                    <div className="w-24 h-24 bg-gray-100 flex flex-wrap p-1.5 gap-1 justify-center items-center rounded-lg">
                      <div className="w-8 h-8 border border-gray-400 bg-gray-800"></div>
                      <div className="w-8 h-8 bg-gray-300"></div>
                      <div className="w-8 h-8 border border-gray-400 bg-gray-800"></div>
                      <div className="w-8 h-8 bg-gray-300"></div>
                    </div>
                    <div className="absolute inset-0 bg-white/95 rounded-xl flex flex-col justify-center items-center text-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <QrCode className="size-5 text-coral mb-0.5 animate-pulse" />
                      <span className="text-[10px] text-coral font-bold font-sans">点击模拟扫码</span>
                    </div>
                  </div>

                  <button
                    onClick={() => setIsFlipped(false)}
                    className="text-xs text-gray-400 hover:text-coral transition-colors"
                  >
                    返回上一步
                  </button>
                </motion.div>
              ) : (
                <motion.div
                  key="success-view"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center justify-center h-full gap-3"
                >
                  <div className="w-14 h-14 rounded-full bg-green-500 flex items-center justify-center text-white shadow-lg">
                    <CheckCircle2 className="size-8 stroke-[2.5]" />
                  </div>
                  <div className="text-center">
                    <h4 className="text-sm font-bold text-charcoal">授权绑定成功</h4>
                    <p className="text-[10px] text-gray-400 mt-1">正在载入文案工作台环境，请稍候...</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
