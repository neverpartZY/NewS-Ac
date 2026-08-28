# -*- coding: utf-8 -*-
"""存储层单测（临时 DB，不污染真实库）。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import storage  # noqa: E402
from pipeline.models import Article  # noqa: E402


def _make_article():
    return Article(
        url_hash=storage.url_hash("https://example.com/news/1"),
        title="惠城环保热解装置满负荷",
        title_zh="惠城环保热解装置满负荷",
        summary_zh="20万吨装置满负荷运行",
        category="enterprise",
        scope="chemical",
        importance=4,
        tags=["化学回收", "热解"],
        source="serper",
        site="example.com",
        url="https://example.com/news/1",
        published_at="2026-08-27",
        collected_at="2026-08-28 08:00:00",
        embedding=np.random.rand(1024).astype(np.float32).tolist(),
        is_price=False,
    )


def test_insert_and_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    a = _make_article()
    assert storage.url_exists(a.url_hash) is False
    storage.insert(a)
    assert storage.url_exists(a.url_hash) is True
    # 重复插入不报错（INSERT OR IGNORE）
    storage.insert(a)
    assert storage.count() == 1


def test_load_for_dedup_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    a = _make_article()
    storage.insert(a)
    rows = storage.load_for_dedup()
    assert len(rows) == 1
    assert rows[0]["url_hash"] == a.url_hash
    emb = rows[0]["embedding"]
    assert emb is not None and emb.shape[0] == 1024
