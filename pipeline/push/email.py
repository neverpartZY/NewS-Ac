# -*- coding: utf-8 -*-
"""邮件推送（Resend HTTP API），正文用精美 HTML 排版 + 纯文本兜底。"""
import config
from . import render
from .base_push import http_post_json

HOST = "https://api.resend.com/emails"


def _send(to, subject, html=None, text=""):
    key = config.get_key("RESEND_API_KEY")
    if not key:
        return {"status": "skip", "reason": "RESEND_API_KEY 未配置"}
    from_addr = config.get_key("FROM_EMAIL") or "塑料循环经济情报中心 <daily@greenplastic.ai>"
    body = {"from": from_addr, "to": to, "subject": subject}
    if html:
        body["html"] = html
    if text:
        body["text"] = text
    r = http_post_json(HOST, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
    if "__error__" in r or "__http_error__" in r:
        return {"status": "error", "detail": r}
    return {"status": "ok", "id": r.get("id")}


def send_report(report_name, markdown, date_str=""):
    """按 config 里的收件人列表群发一份日报。"""
    recipients = config.EMAIL.get("recipients", [])
    if not recipients:
        return {"status": "skip", "reason": "收件人为空"}
    subject = f"♻️ {report_name} · {date_str or '今日'}"
    return _send(recipients, subject, render.render_html(markdown, report_name), markdown)


def send_to(report_name, markdown, to, date_str=""):
    """给单个收件人发一份日报（测试/指定投递）。"""
    if isinstance(to, str):
        to = [to]
    subject = f"♻️ {report_name} · {date_str or '今日'}"
    return _send(to, subject, render.render_html(markdown, report_name), markdown)


def send_alert(subject, text):
    """引擎失效等系统告警：纯文本，发 ALERT_EMAIL（逗号分隔）或回落到日报收件人。"""
    to = [x.strip() for x in (config.get_key("ALERT_EMAIL") or "").split(",") if x.strip()]
    if not to:
        to = config.EMAIL.get("recipients", [])
    if not to:
        return {"status": "skip", "reason": "无告警收件人（ALERT_EMAIL 与 email_recipients 均为空）"}
    return _send(to, subject, text=text)
