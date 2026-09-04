#!/usr/bin/env bash
# 塑料回收日报 · 服务器每日运行入口（cron 调用）
# 用法：cron 里直接调本脚本，或手动 ./run.sh
# 防静默失败（2026-09-01）：非零退出 或 采集失效(alert_no_collection) → 企微群 webhook 告警
# 注意：cron 建议用 `/bin/bash run.sh ...` 调用，执行位丢失也不至于整条任务静默消失
set -uo pipefail
cd "$(dirname "$0")"

mkdir -p logs
LOG="logs/daily_$(date +%Y%m%d).log"

# 取第一个群机器人 webhook 用于告警（读不到就跳过告警，不阻塞主流程）
WEBHOOK_URL=""
if [ -f config/webhook_groups.json ]; then
    WEBHOOK_URL=$(python3 -c "import json;print(json.load(open('config/webhook_groups.json'))['groups'][0]['webhook_url'])" 2>/dev/null || true)
fi

alert() {  # $1 = markdown 文本；用 python 组 JSON+发请求，避开 shell 引号地狱
    [ -n "$WEBHOOK_URL" ] || return 0
    python3 - "$WEBHOOK_URL" "$1" <<'PY' >/dev/null 2>&1 || true
import json, sys, urllib.request
req = urllib.request.Request(sys.argv[1],
    data=json.dumps({"msgtype": "markdown", "markdown": {"content": sys.argv[2]}}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=10)
PY
}

email_alert() {  # $1=主题 $2=正文（纯文本）；发 .env ALERT_EMAIL（逗号分隔），不进群
    "$PY" - "$1" "$2" <<'PY' >/dev/null 2>&1 || true
import sys
from pipeline.push import email
import config
to = [x.strip() for x in (config.get_key("ALERT_EMAIL") or "").split(",") if x.strip()]
if to:
    email._send(to, sys.argv[1], text=sys.argv[2])
PY
}

# 优先用项目内 venv，否则退回系统 python3
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    PY="python3"
fi

# 每日运行前从日报网站后端刷新客户邮件名单（失败不阻塞主流程）
python3 pipeline/push/server_scripts/export_customers.py >> "$LOG" 2>&1 || true

"$PY" main.py "${@:---once}" >> "$LOG" 2>&1
rc=$?

if [ "$rc" -ne 0 ]; then
    alert "🚨 **塑料日报运行失败**（exit $rc）
$(hostname) · $(date '+%F %T')
日志尾部 $LOG：
> $(tail -5 "$LOG" | tr '\n' ';' | cut -c1-300)"
    exit "$rc"
fi

# exit 0 但采集失效（manifest 标记 alert_no_collection）同样要告警，不能装作一切正常
manifest=$(ls -t reports/run_daily_*.json 2>/dev/null | head -1)
if [ -n "$manifest" ] && grep -q 'alert_no_collection' "$manifest"; then
    alert "🚨 **塑料日报采集失效**：今日运行完成但无内容（alert_no_collection）
$(hostname) · $(date '+%F %T')
manifest: $manifest"
fi

# 企微未发（no_doc = 智能文档创建失败；铁律：群里禁止纯文字，宁可不发）
# 用户 2026-09-03 指定：这类技术性告警不发群，私发邮箱（.env ALERT_EMAIL）
if grep -q 'no_doc' "$LOG"; then
    email_alert "⚠️ 塑料日报企微未推送（$(date '+%F %T')）" \
"智能文档创建失败，按铁律未向群里发任何消息（群里禁止纯文字）。
常见原因：wecom-cli 授权过期 → 服务器上重新扫码：
  wecom-cli auth init --noninteractive
授权恢复后补推即可（补推只发文档链接）。
主机: $(hostname)
日志: $(pwd)/$LOG"
fi
