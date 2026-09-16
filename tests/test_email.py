# -*- coding: utf-8 -*-
"""邮件合刊推送单测（mock _send，绝不联网、不进真实收件箱）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.push import email, render  # noqa: E402

REPORTS = {
    "综合日报": "# ♻️ 塑料循环经济综合日报\n\n2026-08-28\n\n## 企业动态\n\n"
                "1. **甲公司**扩产\n   [查看原文](https://a)\n",
    "化学循环日报": "# ♻️ 化学循环日报\n\n2026-08-28\n\n## 政策法规\n\n正文段。\n",
    "再生PET日报": "# ♻️ 再生PET日报\n\n2026-08-28\n\n## 价格行情\n\n正文段。\n",
}


def test_render_merged_contains_all_sections():
    html = render.render_merged_html(REPORTS, "2026-08-28")
    for name in REPORTS:
        assert name in html  # 三份报告各有一个分节头
    assert "日报合刊" in html and "2026-08-28" in html
    assert html.count("合刊") >= 1
    # 合刊头部不再重复各报告的 # 大标题（标题行只以分节头形式出现）
    assert html.count("<!DOCTYPE html>") == 1


def test_render_merged_weekly_naming():
    weekly = {name.replace("日报", "周报"): md.replace("日报", "周报")
              for name, md in REPORTS.items()}
    html = render.render_merged_html(weekly, "2026-08-30")
    assert "周报合刊" in html and "日报合刊" not in html


def test_send_merged_one_call_per_group(monkeypatch, tmp_path):
    """三报合刊：内部一封 + 客户一封，共 2 次 Resend 调用（不是每报一封）。"""
    calls = []

    def fake_send(to, subject, html=None, text=""):
        calls.append({"to": list(to), "subject": subject})
        return {"status": "ok", "id": "x"}

    monkeypatch.setattr(email, "_send", fake_send)
    monkeypatch.setattr(config, "EMAIL", {"recipients": ["team@x.com"]})
    monkeypatch.setattr(config, "CUSTOMER_EMAIL",
                        {"enabled": True, "recipients": ["c1@x.com", "c2@x.com"]})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)

    r = email.send_merged(REPORTS, "2026-08-28")
    assert r["email"]["status"] == "ok"
    assert r["customers"]["status"] == "ok"
    assert len(calls) == 2
    assert calls[0]["to"] == ["team@x.com"]
    assert calls[1]["to"] == ["c1@x.com", "c2@x.com"]
    assert "合刊" in calls[0]["subject"]
    # 防重复状态按合刊粒度落盘（push_state_日期.json）
    state = json.loads((tmp_path / "push_state_2026-08-28.json").read_text(encoding="utf-8"))
    assert state["日报合刊"]["email"]["status"] == "ok"
    assert state["日报合刊"]["email_customers"]["status"] == "ok"


def test_send_merged_dedup(monkeypatch, tmp_path):
    """同日重跑：合刊已发过 → 跳过，不再发送。"""
    calls = []

    def fake_send(to, subject, html=None, text=""):
        calls.append(subject)
        return {"status": "ok", "id": "x"}

    monkeypatch.setattr(email, "_send", fake_send)
    monkeypatch.setattr(config, "EMAIL", {"recipients": ["team@x.com"]})
    monkeypatch.setattr(config, "CUSTOMER_EMAIL", {"enabled": True, "recipients": []})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)

    email.send_merged(REPORTS, "2026-08-28")
    r2 = email.send_merged(REPORTS, "2026-08-28")
    assert len(calls) == 1
    assert r2["email"]["status"] == "skip"
    assert "customers" not in r2  # 客户名单为空，本就不发


def test_send_merged_empty_recipients_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(email, "_send",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应发送")))
    monkeypatch.setattr(config, "EMAIL", {"recipients": []})
    monkeypatch.setattr(config, "CUSTOMER_EMAIL", {"enabled": True, "recipients": ["c@x.com"]})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)

    r = email.send_merged(REPORTS, "2026-08-28")
    assert r["status"] == "skip" and "收件人为空" in r["reason"]
