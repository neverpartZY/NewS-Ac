# -*- coding: utf-8 -*-
"""企业微信推送（对齐真实链路，两段式）：

段1 · Python 自主（零依赖，任何环境直接能跑）：
  群机器人 webhook 发短消息——标题 + 今日核心叙事一句摘要 + （完整版见邮件）。
  群机器人 webhook 与 wecom_mcp 的 msg 品类无关：机器人只需 URL，无需任何授权。

段2 · 智能文档（交接给服务器 OpenClaw）：
  建智能文档走 OpenClaw 企微插件的 wecom_mcp（doc 品类已开通 23 工具；
  msg 未开通 errcode 846610、contact 未开通），凭证由插件在企微管理后台配置，
  Python 无法也不应直连。本程序生成 handoff 文件（smartpage_create 调用参数规格），
  服务器 OpenClaw agent 照单执行创建，拿到 url 后转发到群（agent/人工）。
"""
import json
import re
from pathlib import Path

import config
from .base_push import http_post_json


def doc_name(report_name, date_str):
    """智能文档命名：中文名 + 中文括号日期（wecom 智能文档规范，禁用下划线英文日期）。"""
    return f"塑料循环经济日报·{report_name}（{date_str}）"


def _clean(s, limit):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    return text[:limit] + ("…" if len(text) > limit else "")


def _digest(markdown, limit=140):
    """取「今日核心叙事」第一段非空正文作短摘要（剥掉 **加粗**，截断）。"""
    in_narrative = False
    for ln in markdown.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            in_narrative = "核心叙事" in s
            continue
        if s.startswith("#") or s.startswith("|") or s.startswith(">"):
            continue
        if in_narrative and s:
            return _clean(s, limit)
    # 兜底：全文第一个正文段（跳过标题后紧跟的日期行）
    for ln in markdown.splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "|", ">")) and not re.match(r"^\d{4}[-年/.]", s):
            return _clean(s, limit)
    return "详情见邮件"


def write_handoff(report_name, markdown, date_str):
    """生成智能文档创建交接文件（服务器 OpenClaw agent 执行 wecom_mcp.smartpage_create）。"""
    md_path = config.REPORT_DIR / f"{report_name}_{date_str}.md"
    handoff = {
        "tool": "wecom_mcp.smartpage_create",
        "title": doc_name(report_name, date_str),
        "pages": [{
            "page_title": report_name,
            "content_type": 1,
            "page_filepath": str(md_path) if md_path.exists() else "",
        }],
        "note": ("执行成功取返回的 url 转发到企微群；msg 品类未开通（errcode 846610），"
                 "程序无法自动发群消息，链接由 agent/人工转发"),
    }
    out = config.REPORT_DIR / f"{report_name}_{date_str}_wecom_handoff.json"
    out.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def send_report(report_name, markdown, date_str=""):
    """webhook 发短消息 + 生成智能文档交接文件。返回状态供台账记录。"""
    date_str = date_str or config.today_str()
    groups = config.WEBHOOK.get("groups", [])
    if not groups:
        return {"status": "skip", "reason": "webhook_groups 为空"}

    content = (f"**♻️ {report_name}（{date_str}）**\n{_digest(markdown)}\n"
               f"（完整版见邮件；智能文档链接随后转发）")
    sent = 0
    for g in groups:
        url = g.get("webhook_url", "")
        if not url:
            continue
        r = http_post_json(url, {"Content-Type": "application/json"},
                           {"msgtype": "markdown", "markdown": {"content": content[:4000]}})
        if "__error__" not in r and "__http_error__" not in r:
            sent += 1

    handoff = write_handoff(report_name, markdown, date_str)
    return {"status": "ok", "sent": sent, "smartdoc_handoff": str(handoff)}
