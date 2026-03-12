# Pinch — Amazon Ads API 串接完成報告

**日期：** 2026-03-10
**狀態：** 已連線，測試通過

---

## 完成項目

| 項目 | 狀態 |
|------|------|
| Amazon Ads API 申請與核准 | ✅ |
| OAuth 授權流程（Login with Amazon） | ✅ |
| API 連線測試 | ✅ |
| 23 個廣告帳戶 Profile 成功取得 | ✅ |

---

## 已串接的品牌帳戶（US）

| 品牌 | 帳戶類型 |
|------|---------|
| Daiken Biomedical | Seller |
| DBJ | Seller |
| Geometric Future | Seller |
| Brain Tea | Seller |
| Flux Sunglasses EU | Seller |
| KIJO STUDIO | Seller |
| EHO Prime | Seller |
| SPINMO store | Seller |
| Tentention | Seller |
| Ever Harvest | Seller |
| Elig Brakes | Seller |
| Sierra automobile CO. | Seller |
| WAUNEE | Seller |
| Furnished Housing Elite | Seller |

另外包含 CA、MX 市場共 23 個 profile。

---

## API 能做什麼？對比現在的手動流程

### 1. 自動拉報告（取代手動下載 CSV）

**現在：** 每週手動登入 Amazon Ads 後台 → 逐一下載每個品牌的 SP/SB/SD 報告 → 整理成 CSV
**之後：** 一鍵自動下載所有品牌報告，直接進入分析流程

- Sponsored Products 成效報告
- Sponsored Brands 成效報告
- Sponsored Display 成效報告
- Search Term Report（搜尋詞報告）
- ASIN 銷售報告

**效益：** 每週省下 30-60 分鐘手動操作，消除人為遺漏

### 2. 自動 Bid 調整（取代手動 Bulk 上傳）

**現在：** 分析 TACOS → 手動製作 Bulk xlsx → 上傳到 Amazon 後台 → 等待處理
**之後：** 系統自動分析 + 直接透過 API 調整 bid，即時生效

- 根據 TACOS 規則自動降 bid（硬性規則：永遠不提高 bid）
- 自動暫停超標的 keyword/target
- 調整 campaign budget
- 不再需要 Bulk 檔案

**效益：** 即時反應，不再有 bulk 上傳的延遲（通常 1-4 小時）

### 3. Campaign 管理自動化

**現在：** 手動在 Amazon 後台建立 campaign、設定 targeting
**之後：** 可以用程式批量操作

- 建立 / 修改 / 暫停 Campaign
- 建立 / 修改 Ad Group、Keyword、Product Targeting
- 批量調整 Daily Budget
- 批量新增 Negative Keywords

**效益：** 大量品牌可以同時操作，不用逐一登入切換帳號

### 4. 排程自動化（未來目標）

- 每日自動拉報告 + 分析
- 每週自動產出 Dashboard HTML + Excel
- 異常警報（TACOS 突然飆高、預算快花完）
- 完全不需要人工介入的日常維運

---

## 技術架構

```
Pinch 系統架構

Amazon Ads API  ←→  Pinch (Python)  →  Dashboard (HTML)
                                     →  Excel 報告
                                     →  Cloudflare Pages 自動部署

授權方式：OAuth 2.0 (Login with Amazon)
權限範圍：advertising::campaign_management, advertising::audiences
SDK：python-amazon-ad-api
```

---

## 安全性

- API 憑證（Client Secret、Refresh Token）僅存放在本機 `.env` 檔案
- 不會上傳到 GitHub 或任何公開位置
- 所有 API 操作都有完整的 audit trail

---

## 下一步計畫

| 優先序 | 項目 | 預期效果 |
|--------|------|---------|
| 1 | 自動拉報告 | 取代每週手動下載 CSV |
| 2 | 自動 Bid 調整 | 取代 Bulk xlsx 上傳 |
| 3 | Search Term 自動分析 | 自動找出高效 / 浪費的搜尋詞 |
| 4 | 排程自動化 | 每日自動執行，零人工介入 |

---

*Pinch — AI-powered Amazon PPC management with surgical precision.*
