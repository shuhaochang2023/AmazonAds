# Amazon Ads Bulk Upload — Master Checklist & Error Prevention Guide

**維護者：** Eric @ Furnished Housing Elite LLC  
**最後更新：** 2026-03-08  
**適用品牌：** DAIKEN · DBJ · Geometric Future · Flux AU/DE/UK/US/CA

---

## 目錄

1. [通用規則（所有廣告類型）](#1-通用規則)
2. [SP Sponsored Products](#2-sp-sponsored-products)
3. [SD Sponsored Display](#3-sd-sponsored-display)
4. [SB Sponsored Brands](#4-sb-sponsored-brands)
5. [Bid 調整規則](#5-bid-調整規則)
6. [常見錯誤 & 解決方案](#6-常見錯誤--解決方案)
7. [各品牌 Config](#7-各品牌-config)
8. [上傳前最終檢查表](#8-上傳前最終檢查表)

---

## 1. 通用規則

| 規則 | 說明 |
|------|------|
| **Campaign ID = Campaign Name** | Create 操作時必須相同 |
| **Ad Group ID = Ad Group Name** | Create 操作時必須相同 |
| **Operation 大寫** | `Create`（不是 `create`） |
| **Child ASIN only** | Product Ad 和 Targeting 永遠用 Child ASIN，不用 Parent ASIN |
| **SKU 必填** | Product Ad rows 必須填 SKU，不能只填 ASIN |
| **Campaign 名稱唯一** | 加 timestamp 避免重複（格式：`_YYYYMMDD_HHMM`） |
| **KW 和 PT 分開操作** | Keyword 和 Product Targeting bid 調整必須在不同 sheet/file，不能混在一起 |
| **Bid ≤ Daily Budget** | Bid 不能大於 Campaign 的 Daily Budget |
| **Budget ≥ $1** | Daily Budget 最低 $1 |

---

## 2. SP Sponsored Products

### 2.1 Create 格式（4個 Entity，固定順序）

```
Row 1: Entity = Campaign
Row 2: Entity = Ad Group  
Row 3: Entity = Product Ad      ← 必須有 SKU
Row 4: Entity = Product Targeting 或 Keyword
```

### 2.2 關鍵欄位規則

| 欄位 | 規則 |
|------|------|
| **Start Date** | State=enabled 時留**空白**（不填日期）|
| **Product Targeting Expression** | 欄位名稱必須是這個（不是 "Targeting Expression" 或 "Attributes"）|
| **Expression 格式** | `asin="B0XXXXXXXX"`（要有引號）|
| **SKU** | Product Ad row 必填，來自 Products.csv |
| **Bidding Strategy** | `Dynamic bids - down only` 或 `Fixed bids` |
| **Targeting Type** | `Manual` 或 `Auto` |

### 2.3 Bulk 工作流程（DAIKEN 確認有效 2026-03-07）

**需要 2 個 Input 檔案：**
1. **現有 bulk xlsx** — 取得 Brand Entity ID、brand assets、SKU、現有 campaign 名稱
2. **Search Term Report**（從 Ads Console 單獨下載，不用 bulk 裡的 ST tab）— bulk 的 ST tab 只有短期資料且無 orders，永遠用獨立下載的版本

**產出 2 個 Output 檔案：**
- **File 1**：Bid 調整（KW Update + PT Update，分開兩個 sheet）
- **File 2**：新 Campaign（SP Auto + Broad SKC Create）

### 2.4 SP 常見錯誤

| 錯誤訊息 | 原因 | 解決方案 |
|---------|------|---------|
| `Campaign with the specified name already exists` | Campaign 名稱重複 | 加 timestamp suffix |
| `merchantSku is empty` | Product Ad row 沒有 SKU | 從 Products.csv 補 SKU |
| `Product is ineligible for advertising` | ASIN 太新或未啟用 | 先確認 ASIN 在 Seller Central 是 Active |
| Column not found / wrong column | 欄位名稱錯誤 | 確認是 "Product Targeting Expression"（不是 "Attributes"）|
| Child row fail after parent | Campaign 建立失敗 → Ad Group/Product Ad 連鎖失敗 | 正常現象，修 parent 就好 |
| Bid col index wrong | Bid 寫入到錯誤欄位 | 確認 Bid col index = 27（不是 25）|

---

## 3. SD Sponsored Display

### 3.1 SD 與 SP 的關鍵差異

| 項目 | SP | SD |
|------|----|----|
| **Start Date** | 留空（State=enabled）| **必填** YYYYMMDD |
| **Product Ad SKU** | 必填 | 必填 |
| **Targeting Entity** | Product Targeting | Audience Targeting |
| **Tactic** | 無 | `T00030`（Audiences）|
| **Cost Type** | 無 | `cpc` |
| **Bid Optimization** | 無 | `clicks`（Ad Group level）|

### 3.2 SD Create 格式（4個 Entity）

```
Row 1: Entity = Campaign        ← Start Date 必填 YYYYMMDD
Row 2: Entity = Ad Group        ← Bid Optimization = clicks
Row 3: Entity = Product Ad      ← SKU 必填，ASIN 留空
Row 4: Entity = Audience Targeting ← Expression Type = audience
```

### 3.3 Audience Targeting 格式

```
Expression Type: audience
Expression Value: [18位數 Audience ID]
```

⚠️ **重要：** Audience ID 是 18 位數字，Excel 會自動轉成科學記號（如 `4.21e+17`）。必須用 Amazon 官方 template 下載後填入，或用 openpyxl 強制文字格式寫入。

### 3.4 SD 常見錯誤

| 錯誤 | 原因 | 解決方案 |
|------|------|---------|
| Start Date invalid | SD 不能留空 | 填入 YYYYMMDD 格式 |
| Audience ID 科學記號 | Excel 自動轉換 | 用 Amazon 官方 template |
| Entity = Product Targeting | SD 用錯 Entity | 改成 Audience Targeting |
| Tactic wrong | T00020 是 Remarketing | 改成 T00030 for Audiences |

---

## 4. SB Sponsored Brands

### 4.1 SB 結構（Keyword Update 必須有 Ad Group ID）

```
Row 1: Entity = Campaign   ← Campaign ID = Campaign Name
Row 2: Entity = Keyword    ← 必須填 Ad Group ID（從現有 bulk 取得）
```

⚠️ **重要（2026-03-09 確認）：** SB Keyword 的 Update 操作**必須**填 `Ad Group ID`，否則會報 `"Keyword was specified without an ad group id"` 錯誤。從現有 bulk xlsx 的 `Sponsored Brands Campaigns` sheet 取得每個 Keyword 對應的 Ad Group ID。

### 4.2 SB Campaign 關鍵欄位

| 欄位 | 規則 |
|------|------|
| **Brand Entity ID** | 從現有 bulk 的 Brand Assets 取得（不要猜）|
| **Ad Format** | `Product Collection` |
| **Bid Optimization** | 留**空白**（不填）|
| **Bid Multiplier** | `"0.0%"`（字串格式，帶 % 符號）|
| **State** | `enabled`（小寫）|
| **Budget Type** | `Daily` |
| **Campaign 命名** | 不要加 `_ERIC` suffix |

### 4.3 SB 品牌資產欄位

| 欄位 | 格式 |
|------|------|
| Brand Logo Asset ID | `amzn1.assetlibrary.asset1.XXXXXXXX:version_v1` |
| Custom Image Asset ID | `amzn1.assetlibrary.asset1.XXXXXXXX:version_v1` |
| Landing Page ASINs | 留空（用 store page URL）或填 ASIN |

⚠️ Brand Logo Asset ID 格式必須以 `amzn1.assetlibrary.asset1.` 開頭，不然上傳失敗。

### 4.4 SB 常見錯誤

| 錯誤 | 原因 | 解決方案 |
|------|------|---------|
| Brand Logo format wrong | Asset ID 格式錯 | 確認以 `amzn1.assetlibrary.asset1.` 開頭 |
| Landing Page ASIN = 0 | 填了 "0" | 改成空白 |
| `_ERIC` in campaign name | 命名問題 | 移除 suffix |
| Bid Optimization filled | 不該填 | 留空 |
| `Keyword was specified without an ad group id` | Keyword Update 沒填 Ad Group ID | 從 bulk xlsx 取得 Ad Group ID，每個 Keyword row 必填 |

### 4.5 80Days Brand Entity ID

```
ENTITY1GCEFK17HNV9Y
```

---

## 5. Bid 調整規則

### 5.1 各品牌參數

| 品牌 | TACOS 目標 | Bid 範圍 | 暫停線（TACOS）|
|------|-----------|---------|--------------|
| DAIKEN | 70% | $2.00–$2.50 | 85% |
| DBJ | 15% | $0.55–$0.66 | 25% |
| Geometric Future | 15% | $0.16–$0.21 | 25% |
| Flux (所有市場) | 30% | $0.55 (Sunglasses) / $0.33 (Straps) | 45% |

### 5.2 Bid 調整邏輯（基於 Search Term Report）

| 條件 | 行動 | 調整幅度 |
|------|------|---------|
| ACOS > 暫停線 + Spend > $10 | `state = paused` | — |
| TACOS > 目標 × 1.2 + Spend > $5 | 降 bid | × 0.8 |

**硬性規則：永遠不提高 bid 或 budget。只能降低或暫停。**

### 5.3 安全限制

- **Bid 不能 > Daily Budget**
- **Bid 最低 $0.02**
- **Budget 最低 $1.00**
- **永遠不加 Negative Keywords**（相關搜尋詞）— 高 ACOS 低 orders = 點擊量不足或 listing 轉換問題，加 negative = 完全斷曝光機會

### 5.4 象限行動對應

| 象限 | 條件 | Bulk 行動 |
|------|------|----------|
| ⭐ Star | 低 TACOS + 高 Sales | 維持現狀，不動 bid/budget |
| ❓ Question | 高 TACOS + 高 Sales | 降 CPC bid；暫停 ACOS > 暫停線的 keywords |
| ✂️ Cut | 高 TACOS + 低 Sales | 無 bid 操作（需降價/coupon/sale 策略）|
| 💡 Potential | 低 TACOS + 低 Sales | 新增 SP + SB + SD；低 CPC；lookalike AMC audience |

---

## 6. 常見錯誤 & 解決方案

### 6.1 格式錯誤（最高頻）

```
❌ Campaign ID 不等於 Campaign Name
❌ Start Date 在 SP 裡填了日期（應留空）
❌ Start Date 在 SD 裡留空（必須填 YYYYMMDD）
❌ Product Ad 只填 ASIN，沒有 SKU
❌ Targeting 欄位名稱用 "Attributes" 或 "Targeting Expression"
❌ KW 和 PT bid 調整混在同一個 file
❌ Bid > Daily Budget
❌ Budget < $1
❌ Operation 小寫（"create" 而不是 "Create"）
```

### 6.2 資料類型錯誤（Excel 自動轉換）

```
❌ Start Date: 20260208 → 20260208.0（Excel 加小數點）
❌ Audience ID: 421081579377084527 → 4.21e+17（科學記號）
```

**解決方案：** 永遠用 Amazon 官方 bulk template 下載後填入，或用 openpyxl 強制 NumberFormat = `@`（文字格式）。

### 6.3 Campaign 命名衝突

```
❌ 同名 Campaign 已存在 → "Campaign with the specified name already exists"
```

**解決方案：** Campaign 名稱加 timestamp：`_20260308_1430`

### 6.4 Chain Failure（連鎖失敗）

```
Campaign fail → Ad Group fail → Product Ad fail → Targeting fail
```

這是正常現象。只要修好 parent（Campaign），children 就會一起成功。不需要逐一修每個 row。

---

## 7. 各品牌 Config

### DAIKEN US
- TACOS 目標：70%
- Bid 範圍：$2.00–$2.50
- 暫停線：85% TACOS
- Input：`clients/daiken/input/`
- Bulk Input：`clients/daiken/bulk-input/`
- Bulk Output：`clients/daiken/bulk-output/`

### DBJ US
- TACOS 目標：15%
- Bid 範圍：$0.55–$0.66
- 暫停線：25% TACOS
- VINE Deduction：有（W1–W4）
- Input：`clients/dbj/input/`

### Geometric Future US
- TACOS 目標：15%
- Bid 範圍：$0.16–$0.21
- 暫停線：25% TACOS
- Input：`clients/geo/input/`

### Flux（5 Marketplaces）
- TACOS 目標：30%
- Bid：Sunglasses $0.55 / Straps $0.33
- 暫停線：45% TACOS
- 80Days Brand Entity ID：`ENTITY1GCEFK17HNV9Y`
- Input：`clients/flux/input/{au|uk|de|us|ca}/`

---

## 8. 上傳前最終檢查表

### ✅ 上傳前必確認（每次都做）

**SP:**
- [ ] Campaign ID = Campaign Name（Create 操作）
- [ ] Ad Group ID = Ad Group Name
- [ ] Operation = `Create`（大寫 C）
- [ ] Start Date 留空（State=enabled）
- [ ] 每個 Product Ad 有 SKU
- [ ] 欄位名稱是 `Product Targeting Expression`
- [ ] Expression 格式：`asin="B0XXXXXXXX"`（有引號）
- [ ] KW 調整和 PT 調整在不同 sheet
- [ ] Bid ≤ Daily Budget
- [ ] Budget ≥ $1
- [ ] Campaign 名稱有 timestamp（Create 時）

**SD（除上面 SP 規則外）：**
- [ ] Start Date 填入（YYYYMMDD，不留空）
- [ ] Entity = `Audience Targeting`（不是 Product Targeting）
- [ ] Tactic = `T00030`
- [ ] Cost Type = `cpc`
- [ ] Audience ID 格式正確（18位數，非科學記號）

**SB:**
- [ ] Keyword Update 必須有 Ad Group ID（從 bulk xlsx 取得）
- [ ] Brand Entity ID 從現有 bulk 取得
- [ ] Bid Optimization 留空
- [ ] Bid Multiplier = `"0.0%"`
- [ ] Brand Logo Asset ID 以 `amzn1.assetlibrary.asset1.` 開頭
- [ ] 無 `_ERIC` suffix
- [ ] Campaign 名稱唯一

### ✅ Upload 後確認

- [ ] 看 Error Report — Chain failure 是正常的
- [ ] 確認 Campaign 在 Ads Console 出現
- [ ] 確認 State = enabled
- [ ] 48小時後確認有 Impressions

---

*本文件根據實際操作經驗持續更新。如遇新錯誤請補充到第 6 節。*
