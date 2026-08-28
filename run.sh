#!/usr/bin/env bash
# 塑料回收日报 · 服务器每日运行入口（cron 调用）
# 用法：cron 里直接调本脚本，或手动 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

# 优先用项目内 venv，否则退回系统 python3
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    PY="python3"
fi

mkdir -p logs
"$PY" main.py --once >> "logs/daily_$(date +%Y%m%d).log" 2>&1
