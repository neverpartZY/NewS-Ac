# -*- coding: utf-8 -*-
"""价格点收敛规则单测（三条规则：时效 / 离群值 / 每品种每天上限）。"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from pipeline.engines.price import clean_price_points  # noqa: E402


def _d(days_ago):
    return (config.today_local() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _p(item, price, date, source):
    return {"item": item, "price": str(price), "unit": "元/吨",
            "trend": "", "trend_pct": "", "source": source, "date": date, "title": ""}


def test_rule1_expired_dropped():
    pts = [_p("再生PET瓶片", 7800, _d(1), "a.com"),
           _p("再生PET瓶片", 7900, _d(3), "b.com")]  # 3 天前过期
    out = clean_price_points(pts, days=2)
    assert len(out) == 1 and out[0]["source"] == "a.com"


def test_rule2_outlier_dropped_by_median():
    pts = [_p("再生PET瓶片", 7800, _d(1), "a.com"),
           _p("再生PET瓶片", 7846, _d(1), "b.com"),
           _p("再生PET瓶片", 7922, _d(1), "c.com"),
           _p("再生PET瓶片", 3900, _d(1), "d.com")]  # 偏离中位数 ~50%
    out = clean_price_points(pts, days=2)
    assert all(p["source"] != "d.com" for p in out)  # 离群值丢弃
    assert all(float(p["price"]) > 7000 for p in out)


def test_rule3_max_two_per_day_distinct_sources():
    pts = [_p("再生PP颗粒", 7000, _d(1), "a.com"),
           _p("再生PP颗粒", 7050, _d(1), "a.com"),   # 同日同源 → 去重
           _p("再生PP颗粒", 7100, _d(1), "b.com"),
           _p("再生PP颗粒", 7150, _d(1), "c.com")]   # 同日第 3 个来源 → 淘汰
    out = clean_price_points(pts, days=2)
    assert len(out) == 2
    assert {p["source"] for p in out} == {"a.com", "b.com"}


def test_unparseable_date_dropped():
    pts = [_p("再生PE颗粒", 6000, "", "a.com"),
           _p("再生PE颗粒", 6100, _d(1), "b.com")]
    out = clean_price_points(pts, days=2)
    assert len(out) == 1 and out[0]["source"] == "b.com"
