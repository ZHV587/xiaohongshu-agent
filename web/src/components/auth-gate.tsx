// 登录门禁:未登录锁住整个应用,只显示中文登录页;登录成功才渲染子内容。
// 放在 ThreadProvider/StreamProvider 之外,确保未登录时不会向后端发任何请求。
"use client";

import { ReactNode, useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, type CurrentUser } from "@/lib/auth";

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
    <div className="bg-background flex min-h-screen w-full items-center justify-center p-4">
      <div className="animate-in fade-in-0 zoom-in-95 flex w-full max-w-md flex-col items-center gap-6 rounded-2xl border p-10 shadow-sm">
        <span className="text-5xl">{BRAND.mark}</span>
        <div className="flex flex-col items-center gap-1.5 text-center">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight">
            {BRAND.name}
          </h1>
          <p className="text-muted-foreground text-sm">{BRAND.slogan}</p>
        </div>
        <Button
          size="lg"
          className="bg-primary text-primary-foreground hover:bg-primary/90 mt-2 w-full gap-2"
          onClick={() => loginWithFeishu("/")}
        >
          用飞书登录
        </Button>
        <p className="text-muted-foreground/80 text-center text-xs leading-relaxed">
          登录后即可生成小红书选题与文案。
          <br />
          你的会话仅自己可见。
        </p>
      </div>
    </div>
  );
}
