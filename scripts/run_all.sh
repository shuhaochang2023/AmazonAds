#!/bin/bash
cd ~/amazon-autopilot
echo "=== Amazon Autopilot 週報更新 $(date) ==="
bash scripts/run_daiken.sh
# bash scripts/run_dbj.sh     ← DBJ 之後加
# bash scripts/run_flux.sh    ← Flux 之後加
echo "=== 全部完成 ==="
