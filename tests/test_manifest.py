# -*- coding: utf-8 -*-
"""标准化运行清单单测（外部发送方的唯一对接契约）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline import runner  # noqa: E402


def test_manifest_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    summary = {"collected": 10, "new": 5, "status": "ok",
               "engines": {"ok": ["serper"], "failed": [], "skipped": ["tavily"]}}
    out = runner._write_manifest("daily", summary, {"综合日报": "# md"}, "2026-08-28")
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["period"] == "daily" and data["date"] == "2026-08-28"
    assert data["status"] == "ok"
    assert data["reports"]["综合日报"].endswith("综合日报_2026-08-28.md")
    assert data["stats"] == {"collected": 10, "new": 5}  # 只收数值，字符串/嵌套 dict 排除
    assert data["engines"]["ok"] == ["serper"]


def test_manifest_alert_has_no_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    out = runner._write_manifest("daily", {"status": "alert_no_collection", "collected": 0}, {}, "2026-08-28")
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["status"] == "alert_no_collection"
    assert data["reports"] == {}
