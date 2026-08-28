# -*- coding: utf-8 -*-
"""企微推送单测（webhook 短消息 + 智能文档交接文件；纯函数，不联网）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.push import wecom  # noqa: E402

SAMPLE = """# ♻️ 塑料循环经济综合日报

2026-08-28

## 一、今日核心叙事

**欧盟PPWR法规全面落地**：8月12日起欧盟包装和包装废弃物法规在27个成员国全面适用，要求2030年所有包装可回收，对全球塑料回收产业格局产生深远影响。

**化学回收产业化加速**：利安德巴塞尔在德国安装热解反应器。

## 企业动态

1. **东粤化学20万吨项目恢复生产**
   摘要内容。
"""


def test_doc_name_chinese_convention():
    # 智能文档命名规范：中文名 + 中文括号日期，禁用下划线英文日期
    n = wecom.doc_name("综合日报", "2026-08-28")
    assert "综合日报" in n and "（2026-08-28）" in n and "_" not in n


def test_digest_takes_core_narrative():
    d = wecom._digest(SAMPLE)
    assert "PPWR" in d and "企业动态" not in d
    assert "**" not in d  # 剥掉加粗标记


def test_digest_fallback_first_paragraph():
    md = "# 标题\n\n2026-08-28\n\n这是第一段正文。"
    assert wecom._digest(md) == "这是第一段正文。"


def test_digest_truncated():
    long_md = "# 标题\n\n## 一、今日核心叙事\n\n" + "长" * 300
    d = wecom._digest(long_md, limit=50)
    assert len(d) == 51 and d.endswith("…")


def test_send_report_webhook_and_handoff(monkeypatch, tmp_path):
    """webhook 发短消息（不发全文）+ 生成 smartpage_create 交接文件。"""
    calls = []

    def fake_post(url, headers, body, timeout=30):
        calls.append(body)
        return {"errcode": 0}

    monkeypatch.setattr(wecom, "http_post_json", fake_post)
    monkeypatch.setattr(config, "WEBHOOK",
                        {"groups": [{"name": "g1", "webhook_url": "https://w1"},
                                    {"name": "g2", "webhook_url": "https://w2"}]})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)  # 交接文件写到临时目录

    r = wecom.send_report("综合日报", SAMPLE, "2026-08-28")
    assert r["status"] == "ok" and r["sent"] == 2
    # 短消息：含摘要、不含全文
    content = calls[0]["markdown"]["content"]
    assert "PPWR" in content and "完整版见邮件" in content and len(content) < 500
    # 交接文件：smartpage_create 参数规格
    handoff = Path(r["smartdoc_handoff"])
    assert handoff.exists()
    data = json.loads(handoff.read_text(encoding="utf-8"))
    assert data["tool"] == "wecom_mcp.smartpage_create"
    assert "（2026-08-28）" in data["title"]
    assert data["pages"][0]["content_type"] == 1
