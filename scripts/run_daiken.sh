#!/bin/bash
cd ~/amazon-autopilot
echo "▶ 產生 DAIKEN HTML..."
python3 core/generate_report.py --client daiken
echo "▶ 產生 DAIKEN Excel..."
python3 core/build_excel.py --client daiken
echo "▶ 推到 GitHub..."
git add output/daiken/
git commit -m "DAIKEN update $(date +%Y%m%d)"
git push origin main
echo "✅ 完成！網址：https://amazonads-9k5.pages.dev/daiken"
