// 技術統計報告頁面（Server Component）：於每次請求即時掃描專案統計並渲染互動式儀表板
import type { Metadata } from "next";

import { collectTechReport } from "@/lib/techReportCollector";
import { TechReportsClient } from "./TechReportsClient";
import "./tech-reports.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "技術統計報告 | 揪呷 JOEAT",
  description: "即時彙整專案程式碼、Git 提交紀錄、前後端套件依賴與系統架構統計數據",
};

export default function TechReportsPage() {
  const report = collectTechReport();
  return <TechReportsClient report={report} />;
}
