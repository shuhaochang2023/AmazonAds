# DAIKEN — Campaign Action Log 廣告操作紀錄

## 2026-03-12

### Full Account Restructure — Option D $752/day 全帳戶預算重整（API 執行）
- **Before:** 385 enabled campaigns, $2,065/day total budget
- **After:** 40 enabled campaigns, $752/day total budget (target $750)
- **Method:** 30-day API campaign report (Feb 9–Mar 11) aggregated by campaign → T1/T2/T3 classification
  - T1 (performers): orders > 0 AND ACOS < 200% → KEEP, reallocate budget proportionally
  - T2 (high ACOS): orders > 0 AND ACOS >= 200% → PAUSE
  - T3 (no orders): $0 orders regardless of spend → PAUSE

#### Actions Executed
- **PAUSED 357 campaigns** (saves $1,682/day)
- **KEPT 27 campaigns** — budget reallocated to match Option D targets
- **RE-ENABLED 8 campaigns** — 5 Premium Fish Oil + 3 Multivitamin (were caught in mass pause)
- **RE-ENABLED 3 Bitter Melon campaigns** (new 3/12 campaigns accidentally paused in mass action)

#### Final Budget Allocation
| Product | Campaigns | Budget/day | Target |
|---------|-----------|-----------|--------|
| Kids Fish Oil | 10 | $400 | $400 ✓ |
| Maca | 11 | $160 | $160 ✓ |
| Bitter Melon | 5 | $100 | $100 ✓ |
| Premium Fish Oil | 5 | $30 | $30 ✓ |
| Nattokinase | 4 | $32 | $30 ✓ |
| Lutein | 2 | $20 | $20 ✓ |
| Vitamins | 3 | $10 | $10 ✓ |
| **Total** | **40** | **$752** | **$750** |

### Post-Restructure Bids Check 重整後出價安全檢查（API 執行）
- **Scope:** 40 campaigns, 128 keywords, 72 targets, 46 ad groups
- **Placement boosts:** 0 violations (all ≤ 50%)
- **Keyword bids:** 0 over $5 cap
- **Target bids:** 0 over $5 cap
- **Ad group default bids:** 0 over $5 cap
- **Result:** ✅ ALL CLEAR

### Bitter Melon $100/day Restructure 苦瓜廣告結構重整（API 執行）
- **Trigger:** Client flagged low CVR — 7/260 clicks = 2.69% (category avg 8-12%)
- **Root cause:** 20+ Bulk Auto campaigns cannibalizing each other, $1,558 identifiable waste (49% of spend)

#### Part 1+2: 檢漏 — Pause & Adjust
- **PAUSED 21 campaigns** — all Bulk Auto bid tests (1.89–2.25) + 2 high-budget Autos (2.21, 2.24)
- **Kept 2 campaigns:**
  - `Bulk Auto 2.27` (174999454565139) — discovery engine, budget $17.19 → **$10.00**
  - `SPM B0CPSQYJK4 BX` (370544645159011) — manual campaign, budget $34.35 → **$30.00**
- Subtotal: **$40/day**

#### Part 3: 衝刺 — 3 New Campaigns
- **`BM - SP - Core Exact - 3/12`** (277145911147971) — $25/day
  - 5 exact match KWs: bitter melon capsules ($3.50), supplement ($3.50), pills ($3.00), extract ($3.00), tablets ($2.50)
- **`BM - SP - Combo Exact - 3/12`** (161457857187426) — $20/day
  - 8 exact match KWs: chromium bitter melon, ceylon cinnamon with bitter melon, karela capsules, bitter gourd capsules, diabetic supplements to lower a1c, etc. ($2.00–2.50)
- **`BM - SP - Product Targeting - 3/12`** (17864289337591) — $15/day
  - 3 proven-converting ASINs: B09KCMDGDR ($2.00), B0FCFTV7JT ($2.00), B001F0R04I ($1.50)
- Subtotal: **$60/day**

#### Budget Summary
| Campaign | Daily Budget |
|---|---|
| Bulk Auto 2.27 (discovery) | $10 |
| SPM B0CPSQYJK4 (existing manual) | $30 |
| Core Exact (new) | $25 |
| Combo Exact (new) | $20 |
| Product Targeting (new) | $15 |
| **Total** | **$100/day** |

- **Expected improvement:** CVR 2.69% → 6-8%, waste -74%, ACOS 158% → 70-90%
- **Review date:** 2026-03-19 (7 days)

## 2026-03-10

### Budget Reallocation Option C 全產品線預算重新分配
- **File:** `bulk-output/Budget_Reallocation_OptionC.xlsx` (392 rows)
- Full account budget reallocation based on product-line performance
- 292 budget adjustments + 100 campaigns paused
- **Scale up:** Bitter Melon — 28 campaigns, $87 → $130 (+49.3%)
- **Scale down:** Fish Oil — 101 campaigns, $836 → $402 (-51.9%)
- **Scale down:** Premium Fish — 4 campaigns, $119 → $30 (-74.6%)
- **Scale down:** Lutein — 16 campaigns, $48 → $20 (-58.3%)
- **Scale down:** Maca — 135 campaigns, $433 → $224 (-48.3%)
- **Scale down:** Vitamins — 29 campaigns, $81 → $59 (-26.8%)
- **Scale down:** Nattokinase — 77 campaigns, $154 → $123 (-20.2%)
- **Scale down:** Brand — 2 campaigns, $21 → $10 (-52.4%)
- **Total daily budget:** $1,779 → $998 (-43.9%)

### Kids Fish Oil Basket Cross-Sell 兒童魚油軟糖交互銷售增長策略
- **File:** `bulk-output/DAIKEN_KidsFishOil_BasketPT_20260310_0800.xlsx` (158 rows)
- **CREATE 1 SP Manual campaign** — Product Targeting on market basket ASINs
- Advertised: Kids Fish Oil Gummy × 2 SKUs (B0G7K4CHWG + B0G7K1VC4G, combined 262 orders)
- Targets: 154 product ASINs co-purchased by existing DAIKEN buyers (not new-to-brand)
- Source: 6 months basket analysis (Sep 2025 – Feb 2026), 14 DAIKEN products analyzed
- Budget: $30/day | Default Bid: $1.50 | PT Bid: $1.00 (conservative cross-sell)
- Strategy: Dynamic bids - down only. Warm audience = higher CVR expected
- **Target ASIN breakdown:**
  - DAIKEN cross-sell: Nattokinase, Maca, Bitter Melon, Fish Oil buyers → Kids Fish Oil
  - Health supplements: Bluebonnet L-Theanine (3×), NOW Foods series, Nature Made Vitamin C
  - Eye health: Viteyes AREDS 2 (2×), Nature's Bounty Lutein — health-conscious parents
  - Superfoods: ELMNT Maca Root (3×), Amazing Grass Greens
  - High-frequency co-purchases: Garden of Life Women's Gummy (2×), Zhou Resveratrol (2×), Culturelle Probiotics (2×)

## 2026-03-09

### Budget Rebalance 全帳戶預算重新分配
- **File:** `bulk-output/bulk_budget_adjustment_20260309.xlsx` (286KB)
- Bulk budget adjustment across all active US campaigns based on W5 performance
- **Scale up:** Nattokinase (W5 $3,261, TACOS 27.7%) — increase budget, ride momentum
- **Scale up:** Maca (organic share rising, 19→45 units) — positive trend, increase exposure
- **Stop bleeding:** Kids Fish Oil (TACOS 124%, 5W loss $4,527) — reduce budget + bids
- **Stop bleeding:** Lutein (TACOS 100.6%) — extremely low volume, reduce spend

### Bid Optimization 出價優化（4 Files）
- **File1:** `bulk-output/File1_KW_Bid_Update.xlsx` — SP keyword bid adjustments (high ACOS down, low ACOS winners up)
- **File2:** `bulk-output/File2_PT_Bid_Update.xlsx` — SP product targeting bid adjustments
- **File3:** `bulk-output/File3_SP_New_Campaigns.xlsx` — New SP campaigns for top performers
- **File4:** `bulk-output/File4_SB_Bid_Update.xlsx` — SB Sponsored Brands bid adjustments

## 2026-03-08

### Search Term Report Analysis 搜尋詞報告分析
- Collected SP + SB Search Term Reports for US market
- Identified high-ACOS search terms for negative targeting
- Identified low-ACOS high-conversion terms for bid increases
- Key findings: Nattokinase keywords performing best, Kids Fish Oil broad terms (kids vitamins, kids supplements) ACOS too high — need tightening
- Data fed into 3/9 bid adjustment files
