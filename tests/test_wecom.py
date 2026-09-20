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


def test_help_message_extraction():
    """850003 类型②：help_message 带机器人授权链接（重扫码无效），必须能完整提取。"""
    raw = ('{"errcode": 850003, "errmsg": "authorization expired", "results_json": null, '
           '"help_message": "当前机器人「文档」使用权限已过期\\n'
           '若你是智能机器人创建者，可以[点击这里]'
           '(https://work.weixin.qq.com/ai/aiHelper/authorizationList?from=chat'
           '&aibotid=33776999891279788&str_aibotid=aibg6XZnlSzGGi9sIMAwHqhV2gfs1SPHf0Y&type=1'
           '&hide_more_btn=true)授权当前机器人文档使用权限"}')
    msg = wecom._help_message(raw)
    assert "已过期" in msg and "\\n" not in msg  # \n 已被反转义
    link = wecom._auth_link(msg)
    assert link.startswith("https://work.weixin.qq.com/ai/aiHelper/authorizationList")
    assert link.endswith("hide_more_btn=true")  # 到右括号为止，不吃进后续中文
    # 类型①（无 help_message）不误报
    assert wecom._help_message('{"errcode": 850003, "errmsg": "authorization expired"}') == ""
    assert wecom._auth_link("") == ""


def test_send_report_no_doc_silent(monkeypatch, tmp_path):
    """CLI 不可用：铁律禁止纯文字 → 群里什么都不发（no_doc），只落交接文件。"""
    calls = []

    def fake_post(url, headers, body, timeout=30):
        calls.append(body)
        return {"errcode": 0}

    monkeypatch.setattr(wecom, "cli_ready", lambda: False)
    monkeypatch.setattr(wecom, "http_post_json", fake_post)
    monkeypatch.setattr(config, "WEBHOOK",
                        {"groups": [{"name": "g1", "webhook_url": "https://w1"},
                                    {"name": "g2", "webhook_url": "https://w2"}]})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)  # 交接文件写到临时目录

    r = wecom.send_report("综合日报", SAMPLE, "2026-08-28")
    assert r["status"] == "no_doc"
    assert not calls  # 群里一条都不发（纯文字绝对禁止）
    # 交接文件：smartpage_create 参数规格（供授权恢复后补推/OpenClaw 建文档）
    handoff = Path(r["handoff"])
    assert handoff.exists()
    data = json.loads(handoff.read_text(encoding="utf-8"))
    assert data["tool"] == "wecom_mcp.smartpage_create"
    assert "（2026-08-28）" in data["title"]
    assert data["pages"][0]["content_type"] == 1


def test_send_report_doc_link(monkeypatch, tmp_path):
    """CLI 可用：建智能文档 → webhook 只发「标题+摘要+链接」短消息。"""
    calls = []
    doc_url = "https://doc.weixin.qq.com/smartpage/a1_TEST"

    def fake_post(url, headers, body, timeout=30):
        calls.append(body)
        return {"errcode": 0}

    monkeypatch.setattr(wecom, "cli_ready", lambda: True)
    monkeypatch.setattr(wecom, "create_doc", lambda p, n: {"url": doc_url, "docid": ""})
    monkeypatch.setattr(wecom, "http_post_json", fake_post)
    monkeypatch.setattr(config, "WEBHOOK",
                        {"groups": [{"name": "g1", "webhook_url": "https://w1"}]})
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)

    r = wecom.send_report("综合日报", SAMPLE, "2026-08-28")
    assert r["status"] == "ok_doc_link" and r["sent"] == 1 and r["doc_url"] == doc_url
    content = calls[0]["markdown"]["content"]
    assert doc_url in content and "打开智能文档" in content
    assert "完整版见邮件" not in content and len(content) < 500
