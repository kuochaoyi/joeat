// 預設首頁（/ 與 /index）：作業導覽入口，整合所有主題功能連結、快速工具與操作小幫手
import type { Metadata } from "next";

import { HomeworkHubClient } from "@/components/HomeworkHubClient";
import "./homework-hub.css";

export const metadata: Metadata = {
  title: "作業導覽首頁 | 揪呷 JOEAT",
  description: "揪呷 JOEAT [商管軟體設計-MIS593]-Team 1 作業入口首頁：提供主題功能連結、快速跳轉工具與操作小幫手指南",
};

export default function HomeworkDefaultPage() {
  return <HomeworkHubClient />;
}
