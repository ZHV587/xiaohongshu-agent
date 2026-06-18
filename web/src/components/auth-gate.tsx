// 登录门禁:未登录锁住整个应用,只显示中文登录页;登录成功才渲染子内容。
// 放在 ThreadProvider/StreamProvider 之外,确保未登录时不会向后端发任何请求。
"use client";

import { ReactNode, useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, type CurrentUser } from "@/lib/auth";
import { KeyRound } from "lucide-react";

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false); // 客户端挂载后才判定,避免 SSR 闪烁
  const [authError, setAuthError] = useQueryState("auth_error");

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

  // 未登录:全屏中文登录页,锁住应用。
  return (
    <div 
      className="flex h-screen w-screen items-center justify-center p-4 select-none"
      style={{
        background: "radial-gradient(circle at center, #FFEDF0 0%, #FAF6F0 100%)"
      }}
    >
      <div className="w-[380px] h-[340px]">
        <div className="w-full h-full bg-white/75 backdrop-blur-md border border-white/50 rounded-2xl shadow-2xl p-8 flex flex-col justify-between">
          <div className="flex flex-col items-center text-center gap-3">
            <span className="bg-coral text-white text-3xl size-14 flex items-center justify-center rounded-2xl shadow-md">🍠</span>
            <h2 className="text-xl font-bold tracking-tight text-charcoal font-display">{BRAND.name}</h2>
            <p className="text-xs text-charcoal-light leading-relaxed">
              绑定您的飞书应用与用户身份，解锁多维表格爆款分析、即时协作和自动分发功能。
            </p>
          </div>
          
          <div className="flex flex-col gap-2">
            {/* 真实飞书 OAuth 授权按钮 */}
            <Button
              id="feishu-oauth-login-btn"
              size="lg"
              className="w-full bg-coral hover:bg-coral-hover text-white py-3 px-4 rounded-xl flex items-center justify-center gap-2 font-medium shadow-md transition-all cursor-pointer border-none"
              onClick={() => loginWithFeishu("/")}
            >
              <KeyRound className="size-4" />
              <span>飞书授权登录</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
