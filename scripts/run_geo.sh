#!/bin/bash
cd /Users/koda/amazon-autopilot
echo "▶ 產生 HTML..."
python3 core/generate_report_geo.py
echo "▶ 產生 Excel..."
python3 core/build_excel_geo.py
echo "▶ 複製到部署資料夾..."
mkdir -p geo
cp output/geo/GEO_US_Feb-Mar_2026.html geo/index.html
cp output/geo/20260308_GEO_US_Feb-Mar_2026.xlsx geo/
echo "▶ 推上 GitHub..."
git add geo/
git commit -m "GEO US update $(date +%Y%m%d)"
git push origin main
echo "✅ 完成！https://amazonads-9k5.pages.dev/geo"
