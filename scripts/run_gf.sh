#!/bin/bash
cd /Users/koda/amazon-autopilot
echo "▶ 產生 HTML..."
python3 core/generate_report_gf.py
echo "▶ 產生 Excel..."
python3 core/build_excel_gf.py
echo "▶ 複製到部署資料夾..."
mkdir -p gf
cp output/gf/GF_US_Feb-Mar_2026.html gf/index.html
cp output/gf/20260308_GF_US_Feb-Mar_2026.xlsx gf/
echo "▶ 推上 GitHub..."
git add gf/
git commit -m "GF US update $(date +%Y%m%d)"
git push origin main
echo "✅ 完成！https://amazonads-9k5.pages.dev/gf"
