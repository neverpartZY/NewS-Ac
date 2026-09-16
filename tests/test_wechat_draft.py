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
    _force_scp_branch(monkeypatch, tmp_path)  # 环境无关：服务器上存在直跑脚本也不走直跑分支
    monkeypatch.setattr(wechat_draft, "_ssh_key", lambda: "")
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "handoff" and "publish_meta" in r["reason"]
    assert (tmp_path / "综合日报_2026-08-28_publish_meta.json").exists()


def _force_scp_branch(monkeypatch, tmp_path):
    """把直跑脚本探测指向不存在的路径——否则在白名单服务器上跑测试会误入直跑分支。"""
    monkeypatch.setattr(wechat_draft, "_DIRECT_SCRIPT", tmp_path / "no_such_publish_article_multi.py")


def test_send_report_full_auto(monkeypatch, tmp_path):
    """有私钥：scp 三件套 + ssh 建草稿，解析 media_id。"""
    _force_scp_branch(monkeypatch, tmp_path)
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
    # 草稿箱只留最新一篇：建稿成功后清理同标题旧稿
    assert calls[2][0] == "scp" and calls[2][-2].endswith("cleanup_drafts.py")
    assert calls[3][0] == "ssh" and "cleanup_drafts.py feiliao_newview MEDIA_1" in calls[3][-1]


def test_send_report_ssh_failure(monkeypatch, tmp_path):
    _force_scp_branch(monkeypatch, tmp_path)
    keyf = tmp_path / "txun.pem"
    keyf.write_text("dummy-key")
    monkeypatch.setattr(wechat_draft, "_ssh_key", lambda: str(keyf))
    monkeypatch.setattr(wechat_draft, "_run",
                        lambda cmd, timeout=90: (1, "", "Permission denied"))
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "error" and "scp" in r["reason"]


def test_send_report_direct_on_server(monkeypatch, tmp_path):
    """直跑分支（服务器主路径）：存在直跑脚本 → 本地直接调，_run 带 cwd/env 参数。"""
    dummy = tmp_path / "publish_article_multi.py"
    dummy.write_text("# 直跑脚本占位（测试探测 .exists()）")
    monkeypatch.setattr(wechat_draft, "_DIRECT_SCRIPT", dummy)
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    calls = []

    def fake_run(cmd, timeout=90, **kwargs):
        calls.append((cmd, kwargs))
        if str(wechat_draft._CLEANUP_SCRIPT) in " ".join(cmd):
            return 0, "DRAFT_CLEANUP_DONE 1", ""
        out = ('== draft/add ==\nDRAFT {"errcode":0,"media_id":"MEDIA_DIR_1"}\n'
               'DRAFT_ONLY_DONE media_id=MEDIA_DIR_1 account=feiliao_newview\n')
        return 0, out, ""

    monkeypatch.setattr(wechat_draft, "_run", fake_run)

    r = wechat_draft.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "ok" and r["media_id"] == "MEDIA_DIR_1"
    build_cmd, build_kw = calls[0]
    assert "publish_article_multi.py" in " ".join(build_cmd) and build_kw.get("cwd")
    cleanup_cmd, cleanup_kw = calls[1]
    assert "cleanup_drafts.py" in " ".join(cleanup_cmd) and cleanup_kw.get("env")


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
