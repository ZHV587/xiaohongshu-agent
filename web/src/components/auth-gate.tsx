// 登录门禁:未登录锁住整个应用,只显示中文登录页;登录成功才渲染子内容。
// 放在 ThreadProvider/StreamProvider 之外,确保未登录时不会向后端发任何请求。
"use client";

import { ReactNode, useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Button, Card, Icon } from "@/components/ds";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, type CurrentUser } from "@/lib/auth";

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false); // 客户端挂载后才判定,避免 SSR 闪烁
  const [authError, setAuthError] = useQueryState("auth_error");

  useEffect(() => {
    let active = true;
    getCurrentUser().then((u) => {
      if (active) {
        setUser(u);
        setReady(true);
      }
    });
    return () => {
      active = false;
    };
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
    <main
      style={{
        minHeight: "100vh",
        width: "100vw",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-4)",
        background: "var(--background)",
        color: "var(--text-body)",
        userSelect: "none",
      }}
    >
      <Card
        padding="lg"
        style={{
          width: 380,
          minHeight: 320,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          gap: "var(--space-8)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: "var(--space-3)" }}>
          <span
            style={{
              width: 56,
              height: 56,
              borderRadius: "var(--radius-xl)",
              background: "var(--coral-brand)",
              color: "var(--text-on-primary)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 30,
              boxShadow: "var(--shadow-coral)",
            }}
          >
            🍠
          </span>
          <div>
            <h1 style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: "var(--text-xl)", fontWeight: 800, letterSpacing: "var(--tracking-tight)" }}>
              {BRAND.name}
            </h1>
            <p style={{ margin: "var(--space-2) 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>
              绑定您的飞书应用与用户身份，解锁多维表格爆款分析、即时协作和自动分发功能。
            </p>
          </div>
        </div>

        <Button
          id="feishu-oauth-login-btn"
          size="lg"
          block
          leftIcon={<Icon name="key-round" size={16} />}
          onClick={() => loginWithFeishu("/")}
        >
          飞书授权登录
        </Button>
      </Card>
    </main>
  );
}
