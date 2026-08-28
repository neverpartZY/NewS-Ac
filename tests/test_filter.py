# -*- coding: utf-8 -*-
"""过滤层纯函数单测（不依赖网络/LLM）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import filter as f  # noqa: E402
from pipeline.models import Candidate  # noqa: E402


def test_is_stale_strong():
    assert f.is_stale("塑料回收行业周报（8月第4周）") is True
    assert f.is_stale("2026年上半年再生塑料盘点回顾") is True
    assert f.is_stale("Weekly digest of plastics recycling") is True


def test_is_stale_fresh_action_release():
    # 时间词 + 披露动词 = 旧事件新披露 → 放行
    assert f.is_stale("公司发布2026年上半年经营总结：再生料产能翻倍") is False


def test_date_in_window():
    from datetime import datetime, timedelta
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    old = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    assert f.date_in_window(recent, 3) == (True, True)
    assert f.date_in_window(old, 3) == (True, False)
    assert f.date_in_window("", 3) == (False, False)


def test_date_in_window_relative():
    # 相对时间须被识别为「有日期的旧闻」，而不是「无日期降级保留」
    assert f.date_in_window("5 days ago", 3) == (True, False)   # 5天前 → 超窗口丢弃
    assert f.date_in_window("1 day ago", 3) == (True, True)     # 1天前 → 在窗口内
    assert f.date_in_window("2 hours ago", 3) == (True, True)   # 几小时前 → 在窗口内
    assert f.date_in_window("2 weeks ago", 3) == (True, False)  # 2周前 → 超窗口丢弃


def test_date_in_window_chinese():
    # 中文相对时间（Serper 对中文结果返回的格式）
    assert f.date_in_window("5天前", 3) == (True, False)    # 5天前 → 超窗口丢弃
    assert f.date_in_window("1天前", 3) == (True, True)     # 1天前 → 在窗口内
    assert f.date_in_window("2小时前", 3) == (True, True)   # 几小时前 → 在窗口内
    assert f.date_in_window("昨天", 3) == (True, True)      # 昨天 → 在窗口内
    assert f.date_in_window("3周前", 3) == (True, False)    # 3周前 → 超窗口丢弃


def test_date_filter_drops_undated():
    # 无日期 = 时效不可证（引擎 7 天窗口会放进旧闻）→ 宁缺毋滥直接丢
    d = Candidate(title="某再生塑料新闻", url="https://e.com/a")
    kept, dropped = f.date_filter([d], 3)
    assert kept == [] and dropped == 1


def test_has_cjk():
    assert f.has_cjk("再生塑料价格") is True
    assert f.has_cjk("rPET price today") is False


def test_hard_noise_filter():
    docs = [
        Candidate(title="乙二醇期货主力合约涨停", snippet="PTA 期货盘面"),
        Candidate(title="某公司回收解决方案", snippet=""),
        Candidate(title="再生PET瓶片价格上涨", snippet="rPET 报价"),
    ]
    kept = f.hard_noise_filter(docs)
    # 第一条命中 hard_noise（期货/涨停）丢；第二条命中 content_noise（解决方案）丢；第三条保留
    assert len(kept) == 1
    assert "再生PET" in kept[0].title
