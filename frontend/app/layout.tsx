import type { Metadata, Viewport } from "next";
import { Noto_Sans_TC } from "next/font/google";

import { ToastProvider } from "@/components/Toast";
import "./globals.css";

const notoSansTC = Noto_Sans_TC({
  subsets: ["latin"],
  weight: ["400", "500", "700", "900"],
  variable: "--font-noto-sans-tc",
  display: "swap",
});

export const metadata: Metadata = {
  title: "揪呷 JOEAT",
  description: "多人聚餐，30 秒一起決定吃什麼",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className={notoSansTC.variable}>
      <body className="antialiased">
        <ToastProvider>
          <main>{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
