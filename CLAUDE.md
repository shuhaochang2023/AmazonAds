# Amazon Autopilot — Claude Code 任務說明

你是一個 Amazon 廣告報告自動化助理。

## 每週標準任務
1. 確認 clients/daiken/input/ 裡有最新的 CSV
2. 在 clients/daiken/config.py 加入新週次（WEEK_RANGES + W_LABELS）
3. 執行：python3 core/generate_report.py --client daiken
4. 執行：python3 core/build_excel.py --client daiken
5. git push 到 GitHub → Cloudflare 自動部署

## 注意事項
- FROZEN_WEEKS 裡的週次絕對不要重新計算
- 每次只加最新一週
- push 前確認 output/daiken/index.html 大小 > 40KB
- Excel 檔名格式：YYYYMMDD_DAIKEN_US_Feb-Mar_2026.xlsx

## 新增品牌
1. 複製 clients/daiken/ → clients/{新品牌}/
2. 修改 config.py
3. 放入 CSV
4. 更新 output/{新品牌}/index.html
5. 在根目錄 index.html 加品牌卡片
