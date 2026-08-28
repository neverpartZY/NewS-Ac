# -*- coding: utf-8 -*-
"""公众号草稿箱推送单测（mock scp/ssh，不真连服务器）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.push import wechat_draft  # noqa: E402

MD = "# ♻️ 塑料循环经济综合日报\n\n2026-08-28\n\n## 一、今日核心叙事\n\n**测试**：内容。\n"


def test_send_report_handoff_without_key(monkeypatch, tmp_path):
    """无私钥：降级为交接文件模式。"""
    monkeypatch.setattr(wechat_draft, "_ssh_key", lambda: "")
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "handoff" and "publish_meta" in r["reason"]
    assert (tmp_path / "综合日报_2026-08-28_publish_meta.json").exists()


def test_send_report_full_auto(monkeypatch, tmp_path):
    """有私钥：scp 三件套 + ssh 建草稿，解析 media_id。"""
    calls = []
    keyf = tmp_path / "txun.pem"
    keyf.write_text("dummy-key")  # 需真实存在的文件，过 Path.exists() 预检查

    def fake_run(cmd, timeout=90):
        calls.append(cmd)
        if cmd[0] == "scp":
            return 0, "", ""
        # 模拟真实多行输出（含 COVER 行的 JSON 噪声）
        out = ('== account: feiliao_newview ==\n== upload cover ==\n'
               'COVER {"errcode":0,"media_id":"COVER_1","url":"http://mmbiz/x"}\n'
               '== no body image, skip ==\n== draft/add ==\n'
               'DRAFT {"errcode":0,"media_id":"MEDIA_1"}\n'
               'DRAFT_ONLY_DONE media_id=MEDIA_1 account=feiliao_newview\n')
        return 0, out, ""

    monkeypatch.setattr(wechat_draft, "_ssh_key", lambda: str(keyf))
    monkeypatch.setattr(wechat_draft, "_run", fake_run)
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)

    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "ok" and r["media_id"] == "MEDIA_1"
    scp_cmd = calls[0]
    assert scp_cmd[0] == "scp" and "-i" in scp_cmd and scp_cmd[-1].endswith(":/home/ubuntu/")
    assert sum(1 for c in scp_cmd if c.endswith(".json")) == 1
    ssh_cmd = calls[1]
    assert ssh_cmd[0] == "ssh" and "publish_article_multi.py publish_meta.json" in ssh_cmd[-1]


def test_send_report_ssh_failure(monkeypatch, tmp_path):
    keyf = tmp_path / "txun.pem"
    keyf.write_text("dummy-key")
    monkeypatch.setattr(wechat_draft, "_ssh_key", lambda: str(keyf))
    monkeypatch.setattr(wechat_draft, "_run",
                        lambda cmd, timeout=90: (1, "", "Permission denied"))
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "error" and "scp" in r["reason"]


def test_parse_result_realistic_output():
    out = ('COVER {"errcode":0,"media_id":"COVER_1"}\n'
           'DRAFT {"errcode":0,"media_id":"MEDIA_1"}\n'
           'DRAFT_ONLY_DONE media_id=MEDIA_1 account=feiliao_newview\n')
    assert wechat_draft._parse_result(out) == "MEDIA_1"
    assert wechat_draft._parse_result("no media here") is None
    assert wechat_draft._parse_result("") is None


def test_placeholder_cover_png(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    p = wechat_draft._cover("综合日报", "2026-08-28")
    data = Path(p).read_bytes()
    assert data.startswith(b"\x89PNG") and len(data) > 100


def test_prepare_meta_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    meta_path, files = wechat_draft.prepare("综合日报", MD, "2026-08-28")
    meta = __import__("json").loads(Path(meta_path).read_text(encoding="utf-8"))
    assert meta["mp_account"] == "feiliao_newview"
    assert meta["content_html"] == "debug-final.html"
    assert "2026-08-28" in meta["title"]
    assert len(files) == 3
