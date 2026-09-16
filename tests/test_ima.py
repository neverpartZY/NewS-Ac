# -*- coding: utf-8 -*-
"""IMA 推送单测：交接模式（唯一路径）——始终生成 handoff 文件，不联网。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.push import ima  # noqa: E402

MD = "# ♻️ 综合日报\n\n2026-08-28\n\n内容。"


def test_send_report_always_handoff(monkeypatch, tmp_path):
    """断言兜底默认值（环境无关）：无 .env 配置时写入实测有效的正确 ID。"""
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(config, "get_key", lambda k: None)  # 屏蔽环境 .env，专测代码兜底
    r = ima.send_report("综合日报", MD, "2026-08-28")
    assert r["status"] == "handoff"
    p = tmp_path / "综合日报_2026-08-28_ima_handoff.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["kb_id"] == "cbS6_lBGSoDYC6oH9t2e-7yN6SbUQkGodQAstAulh5s="  # 国嘉基业·LLM Wiki（实测有效 ID）
    assert data["folder_id"] == "7471548801773576"   # 日报文件夹
    assert data["file_name"] == "综合日报_2026-08-28.md"
    assert data["content_markdown"] == MD
    assert "ima-mcp" in data["tool"]


def test_handoff_prefers_env_config(monkeypatch, tmp_path):
    """.env 配置优先于代码兜底（服务器实际走的就是这条路径）。"""
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    env = {"IMA_KB_ID": "KB_FROM_ENV", "IMA_FOLDER_ID": "FOLDER_FROM_ENV"}
    monkeypatch.setattr(config, "get_key", lambda k: env.get(k))
    ima.send_report("综合日报", MD, "2026-08-28")
    data = json.loads(
        (tmp_path / "综合日报_2026-08-28_ima_handoff.json").read_text(encoding="utf-8"))
    assert data["kb_id"] == "KB_FROM_ENV" and data["folder_id"] == "FOLDER_FROM_ENV"


def test_handoff_uses_today_when_no_date(monkeypatch, tmp_path):
    import config as cfg
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    ima.send_report("综合日报", MD)
    p = tmp_path / f"综合日报_{cfg.today_str()}_ima_handoff.json"
    assert p.exists()
