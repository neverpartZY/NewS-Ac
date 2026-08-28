# -*- coding: utf-8 -*-
"""引擎健康判断单测（区分「引擎失效」与「无新闻」——旧系统空转兜底规则）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline import runner  # noqa: E402


def test_engine_health(monkeypatch):
    # serper 有 key；tavily / gzh 无 key
    monkeypatch.setattr(config, "get_key", lambda name: "k" if name == "SERPER_API_KEY" else "")
    monkeypatch.setattr(runner.gzh, "_key", lambda: "")
    stats = {
        "serper": {"queries": 20, "docs": 0},   # 有 key 有查询 0 产出 → 疑似失效
        "tavily": {"queries": 20, "docs": 0},   # 无 key → 跳过
        "gzh": {"queries": 1, "docs": 0},       # 无 key → 跳过
        "site": {"queries": 1, "docs": 0},      # 衍生通道视为有 key → 疑似失效
    }
    failed, skipped, ok = runner._engine_health(stats)
    assert failed == ["serper", "site"]
    assert skipped == ["tavily", "gzh"]
    assert ok == []


def test_engine_health_ok(monkeypatch):
    monkeypatch.setattr(config, "get_key", lambda name: "k")
    monkeypatch.setattr(runner.gzh, "_key", lambda: "k")
    stats = {"serper": {"queries": 20, "docs": 50}, "gzh": {"queries": 1, "docs": 168}}
    failed, skipped, ok = runner._engine_health(stats)
    assert failed == [] and skipped == [] and ok == ["serper", "gzh"]


def test_engine_health_no_query_means_not_failed(monkeypatch):
    # 配了 key 但本轮没跑任何查询（freqs 过滤）→ 不算失效
    monkeypatch.setattr(config, "get_key", lambda name: "k")
    monkeypatch.setattr(runner.gzh, "_key", lambda: "k")
    failed, skipped, ok = runner._engine_health({"tavily": {"queries": 0, "docs": 0}})
    assert failed == [] and ok == ["tavily"]


def test_alert_markdown_contains_status():
    md = runner._alert_markdown({"serper": {"queries": 5, "docs": 0}}, ["serper"], [], "2026-08-28")
    assert "疑似失效" in md and "serper" in md and "2026-08-28" in md
