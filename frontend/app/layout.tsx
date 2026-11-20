import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = { title: "揪呷 JOEAT", description: "多人聚餐，一起決定吃什麼" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body><main>{children}</main></body>
    </html>
  );
}
