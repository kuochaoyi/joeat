# 店家聲明試辦套件

要找真實店家試辦,**從這裡開始**。這個資料夾是我(AI)能準備的部分;**打電話、找法務、架站、備份只有你能做**。

| 檔案 | 內容 |
|---|---|
| [01_pilot_plan.md](01_pilot_plan.md) | 試辦要回答的 5 個問題、規模、節奏、**停止條件**、風險 |
| [02_candidates.md](02_candidates.md) / `.csv` | 從資料庫自動產生的候選名單與每家的通話前資料(重跑 `scripts/pilot_candidates.py` 會覆蓋) |
| [03_call_script.md](03_call_script.md) | 電話話術、訊息範本、**一定不要說的話** |
| [03b_pilot_log_template.csv](03b_pilot_log_template.csv) | 你每家要記錄的欄位 |
| [04_operator_runbook.md](04_operator_runbook.md) | 每天的審核、撤下、事故處理 |
| [05_go_live_checklist.md](05_go_live_checklist.md) | 上線前的阻擋項、建議、已知缺口 |
| [06_legal_review_brief.md](06_legal_review_brief.md) | **給律師的簡報**:所有法律相關文字逐字、事實、14 個待答問題、我們自己發現的問題 |

工具(都在 `backend/scripts/`):

```bash
python scripts/pilot_preflight.py              # 這個環境能不能給真店家用?有阻擋項時退出碼 1
python scripts/pilot_candidates.py             # 重新產生候選名單
python scripts/pilot_metrics.py                # 試辦指標(漏斗、時間、共用設備答案分布)
python scripts/seed.py --reset --no-fixtures   # 試辦用的乾淨資料庫(已有真實認領時拒絕執行)
```

**現在的狀態(誠實版)**:預檢有 6 個阻擋項(法務、https 網址、金鑰 ×2、示範旗標、示範資料)。在它們全部解掉之前,不要把任何連結交給真實店家。
