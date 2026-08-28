# -*- coding: utf-8 -*-
"""企业微信推送：群机器人 webhook（markdown）。"""
import config
from .base_push import http_post_json


def send_report(report_name, markdown, date_str=""):
    groups = config.WEBHOOK.get("groups", [])
    if not groups:
        return {"status": "skip", "reason": "webhook_groups 为空"}
    # markdown 超长需截断（企业微信单条上限约 4096 字节）
    content = markdown[:3800]
    sent = 0
    for g in groups:
        url = g.get("webhook_url", "")
        if not url:
            continue
        r = http_post_json(url, {"Content-Type": "application/json"},
                           {"msgtype": "markdown", "markdown": {"content": f"**♻️ {report_name}**\n\n{content}"}})
        if "__error__" not in r and "__http_error__" not in r:
            sent += 1
    if sent == 0:
        return {"status": "error", "reason": "webhook 全部失败"}
    return {"status": "ok", "sent": sent}
