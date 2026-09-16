# -*- coding: utf-8 -*-
"""邮件推送（Resend HTTP API），正文用精美 HTML 排版 + 纯文本兜底。"""
import config
from . import render, state
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


def send_merged(reports, date_str=""):
    """全部报告合并为一封「合刊」邮件（省收件箱，也省 Resend 配额）。

    reports: dict[报告名 -> markdown]。内部一封、客户一封（共 2 次 Resend 调用），
    客户列表失败不影响内部投递。防重复（push_state）按合刊粒度记录：
    今日合刊已成功发过 → 跳过（手动重跑不会重复轰炸收件人）。
    """
    date_str = date_str or config.today_str()
    recipients = config.EMAIL.get("recipients", [])
    if not recipients:
        return {"status": "skip", "reason": "收件人为空"}

    names = list(reports.keys())
    suffix = "周报" if names and all("周报" in n for n in names) else "日报"
    key = f"{suffix}合刊"
    subject = f"♻️ 塑料循环经济{suffix}合刊 · {date_str}"
    html = render.render_merged_html(reports, date_str)
    text = "\n\n---\n\n".join(reports.values())

    result = {}
    prev = state.get(date_str, key, "email")
    if prev and prev.get("status") == "ok":
        result["email"] = {"status": "skip", "reason": "今日已推送过邮件（push_state 防重复）"}
    else:
        result["email"] = _send(recipients, subject, html=html, text=text)
        state.record(date_str, key, "email", status=result["email"].get("status"))

    customers = config.CUSTOMER_EMAIL.get("recipients", [])
    if config.CUSTOMER_EMAIL.get("enabled", True) and customers:
        # 客户单独一封（同一合刊排版），不与内部混发，便于统计/停发
        cprev = state.get(date_str, key, "email_customers")
        if cprev and cprev.get("status") == "ok":
            result["customers"] = {"status": "skip", "reason": "今日已推送（防重复）"}
        else:
            result["customers"] = _send(customers, subject, html=html, text=text)
            state.record(date_str, key, "email_customers",
                         status=result["customers"].get("status"))
    return result


def send_report(report_name, markdown, date_str=""):
    """单报发送（push_all 已改走 send_merged 合刊；此函数保留给指定单报投递/补推）。

    内部团队（email_recipients.json）与网站注册客户（email_recipients_customers.json）
    分两次 Resend 调用发送：客户列表失败不影响内部投递，两边状态都能观测。
    防重复（push_state）：今日该报告已成功发过邮件 → 跳过（手动重跑不会重复轰炸收件人）。
    """
    date_str = date_str or config.today_str()
    recipients = config.EMAIL.get("recipients", [])
    if not recipients:
        return {"status": "skip", "reason": "收件人为空"}

    prev = state.get(date_str, report_name, "email")
    if prev and prev.get("status") == "ok":
        result = {"status": "skip", "reason": "今日已推送过邮件（push_state 防重复）"}
    else:
        subject = f"♻️ {report_name} · {date_str or '今日'}"
        result = _send(recipients, subject, render.render_html(markdown, report_name), markdown)
        state.record(date_str, report_name, "email", status=result.get("status"))

    customers = config.CUSTOMER_EMAIL.get("recipients", [])
    if config.CUSTOMER_EMAIL.get("enabled", True) and customers:
        # 客户单独一封（同一排版），不与内部混发，便于统计/停发
        cprev = state.get(date_str, report_name, "email_customers")
        if cprev and cprev.get("status") == "ok":
            result["customers"] = {"status": "skip", "reason": "今日已推送（防重复）"}
        else:
            subject = f"♻️ {report_name} · {date_str or '今日'}"
            result["customers"] = _send(customers, subject,
                                        render.render_html(markdown, report_name), markdown)
            state.record(date_str, report_name, "email_customers",
                         status=result["customers"].get("status"))
    return result


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
