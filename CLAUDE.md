# Amazon Autopilot — Claude Code 任務說明

你是一個 Amazon 廣告報告自動化助理。

## 部署
- GitHub repo → Cloudflare Pages 自動部署
- Live URL: https://amazonads-9k5.pages.dev/
- git push origin main 後自動上線
- HTML 變更完成後直接 push，不用問

## 專案結構

```
amazon-autopilot/
├── index.html                    # 首頁（品牌卡片列表）
├── CLAUDE.md                     # ← 你現在在讀的
├── docs/
│   └── Amazon_Ads_Bulk_Checklist.md  # Bulk 上傳規則（SP/SD/SB）
├── core/                         # 報告產生器（Python）
│   ├── generate_report.py        # DAIKEN 報告
│   ├── generate_report_dbj.py    # DBJ 報告
│   ├── generate_report_geo.py    # Geometric Future 報告
│   ├── generate_report_flux.py   # Flux 多市場報告
│   ├── build_excel.py            # DAIKEN Excel
│   ├── build_excel_dbj.py        # DBJ Excel
│   ├── build_excel_geo.py        # GEO Excel
│   ├── build_excel_flux.py       # Flux Excel（5市場）
│   └── bulk_processor_daiken.py  # DAIKEN bulk bid 調整
├── scripts/
│   ├── run_daiken.sh
│   ├── run_dbj.sh
│   ├── run_geo.sh
│   └── run_flux.sh
├── clients/                      # 品牌原始資料
│   ├── daiken/
│   │   ├── config.py             # WEEK_RANGES, W_LABELS, FROZEN_WEEKS
│   │   ├── input/                # CSV: HistoricalAsinDateSales, Products, SB_report
│   │   ├── bulk-input/           # Bulk xlsx + Search Term Reports
│   │   └── bulk-output/          # 產出的 bid 調整 xlsx
│   ├── dbj/input/
│   ├── geo/input/
│   └── flux/input/{au,uk,de,us,ca}/   # 每市場各一組 CSV
├── output/                       # 產出的 HTML + Excel（git tracked）
│   ├── daiken/
│   ├── dbj/
│   ├── geo/
│   └── flux/                     # au.html, uk.html, de.html, us.html, ca.html, index.html
├── daiken/index.html             # Cloudflare 部署用（含下載按鈕）
├── dbj/index.html
├── geo/index.html
├── brain-tea/index.html
├── flux/                         # Flux 多市場 dashboard
│   ├── index.html                # Tab 切換（AU/UK/DE/US/CA）
│   ├── au.html, uk.html, de.html, us.html, ca.html
│   └── *.xlsx                    # 各市場 Excel
├── flux-{au,uk,de,us,ca}/index.html  # 各市場獨立頁面
├── apal/                         # APAL（Social Listening / YouTube）
├── kijo/                         # KIJO（即將上線）
└── geometric-future/index.html   # redirect → geo/
```

## 品牌一覽

| 品牌 | 市場 | TACOS 目標 | Bid 範圍 | 暫停線 | 狀態 |
|------|------|-----------|---------|--------|------|
| DAIKEN | US | 70% | $2.00–$2.50 | 85% | LIVE |
| DBJ | US | 15% | $0.55–$0.66 | 25% | LIVE |
| Geometric Future (GEO) | US | 15% | $0.16–$0.21 | 25% | LIVE |
| Brain Tea | US | 15% | $0.50–$0.60 | 28% | LIVE |
| Flux | AU/UK/DE/US/CA | 30% | $0.55 (Sunglasses) / $0.33 (Straps) | 45% | LIVE |
| APAL | — | — | — | — | Social Listening |
| KIJO | US | — | — | — | 即將上線 |

## 每週標準任務

### 單市場品牌（DAIKEN / DBJ / GEO）
1. 確認 clients/{brand}/input/ 裡有最新的 CSV（HistoricalAsinDateSales, Products, SB_report）
2. 在 clients/{brand}/config.py 加入新週次（WEEK_RANGES + W_LABELS）
3. 執行對應的 generate_report + build_excel
4. git push → Cloudflare 自動部署

### Flux（多市場）
1. 確認 clients/flux/input/{au,uk,de,us,ca}/ 各有 3 個 CSV
2. 執行：`python3 core/generate_report_flux.py`
3. 執行：`python3 core/build_excel_flux.py`
4. 或直接：`bash scripts/run_flux.sh`
5. git push → 部署

## 注意事項
- FROZEN_WEEKS 裡的週次絕對不要重新計算
- 每次只加最新一週
- push 前確認 HTML 大小 > 40KB
- Excel 檔名格式：YYYYMMDD_{BRAND}_{MARKET}_Feb-Mar_2026.xlsx

## 報告產出必檢項目（每次、每個品牌）
1. **SB 廣告費**：HistoricalAsinDateSales 裡 ASIN="Sponsored Brands Product Collection/Brand Video" 的 PPC Cost 必須納入 TACOS 計算，按 SB Attributed Sales 比例分配到各 parent
2. **HTML = Excel**：產出後驗證 HTML 和 Excel 的產品名稱、Sales、Spend、TACOS 完全一致
3. **產品名稱**：不能只顯示 ASIN，必須有可辨認的短名稱（從 Products.csv 取得，parent 用 child title 作 fallback）
4. **下載按鈕**：每次重新產生 HTML 後要重新注入 Excel 下載按鈕

## Bulk File 任務
- 任何涉及 bulk file 的任務，先讀 `docs/Amazon_Ads_Bulk_Checklist.md`，按照 checklist 建立 bulk file
- 輸入放 clients/{品牌}/bulk-input/，輸出放 clients/{品牌}/bulk-output/
- Flux Brand Entity ID (80Days): `ENTITY1GCEFK17HNV9Y`

## 新增品牌
1. 建立 clients/{新品牌}/input/
2. 複製並修改對應的 generate_report + build_excel
3. 建立 scripts/run_{brand}.sh
4. 建立 {brand}/index.html（部署用）
5. 在根目錄 index.html 加品牌卡片

## Bid 調整邏輯
| 條件 | 行動 |
|------|------|
| ACOS > 暫停線 + Spend > $10 | state = paused |
| TACOS > 目標 × 1.2 + Spend > $5 | 降 bid × 0.8 |

**硬性規則：永遠不提高 bid 或 budget。只能降低或暫停。**

安全限制：Bid ≤ Daily Budget、Bid ≥ $0.02、Budget ≥ $1.00、永遠不加 Negative Keywords、永遠不提高 bid/budget
