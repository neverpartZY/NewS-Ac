# -*- coding: utf-8 -*-
"""加工层护栏单测：LLM 返回脏值（中文数字/字符串 tags/乱值 scope）不崩整轮。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.models import Candidate  # noqa: E402
from pipeline.refine import _article, _norm_scope  # noqa: E402


def _doc():
    return Candidate(title="原始标题", url="https://e.com/a", url_hash="h",
                     engine="gzh", site="e.com", snippet="s" * 150, date="2小时前")


def test_dirty_llm_values_fall_back():
    a = _article(_doc(), {"importance": "高", "tags": "回收, PET、化学", "scope": "化学回收"})
    assert a.importance == 3
    assert a.tags == ["回收", "PET", "化学"]
    assert a.scope == "chemical"
    assert a.title_zh == "原始标题"  # title_zh 缺失回落原题


def test_importance_clamped():
    assert _article(_doc(), {"importance": 9}).importance == 5
    assert _article(_doc(), {"importance": 0}).importance == 1


def test_norm_scope():
    assert _norm_scope("chemical") == "chemical"
    assert _norm_scope("rPET") == "rpet"
    assert _norm_scope("热解相关") == "chemical"
    assert _norm_scope("PET瓶片新闻") == "rpet"
    assert _norm_scope("随便") == "general"
    assert _norm_scope("") == "general"


def test_scope_hint_authoritative():
    d = _doc()
    d.scope_hint = "rpet"
    a = _article(d, {"scope": "化学回收"})  # LLM 判错也不进错报
    assert a.scope == "rpet"
