import type { Metadata } from "next";
import "./globals.css";
import React from "react";
import { NuqsAdapter } from "nuqs/adapters/next/app";

// Next.js app layouts are expected to export metadata alongside the component.
// eslint-disable-next-line react-refresh/only-export-components
export const metadata: Metadata = {
  title: "小红书文案助手",
  description: "你的小红书爆款搭子🍠",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="font-sans antialiased">
        <NuqsAdapter>{children}</NuqsAdapter>
      </body>
    </html>
  );
}
