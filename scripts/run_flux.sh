#!/bin/bash
cd /Users/koda/amazon-autopilot
echo "▶ 產生 Flux Multi-Market HTML..."
python3 core/generate_report_flux.py
echo "▶ 推上 GitHub..."
git add -f flux/ output/flux/ core/generate_report_flux.py scripts/run_flux.sh clients/flux/
git commit -m "Flux update $(date +%Y%m%d)"
git push origin main
echo "✅ 完成！https://amazonads-9k5.pages.dev/flux"
