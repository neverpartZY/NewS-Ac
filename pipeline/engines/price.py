# -*- coding: utf-8 -*-
"""价格管道：从搜索结果文本提取再生料「参考价格点」（非实时行情，可溯源参考价）。

生意社/隆众/卓创的结构化价格 API 均为付费墙，故从 Serper/Tavily 搜索结果文本里
正则提取价格点，聚合成带来源+日期的参考价格表。
"""
import re

import config
from . import serper as serper_engine
from . import tavily as tavily_engine

PRICE_PATTERNS = [
    (r'([\d,]{3,6})\s*[-~～至]\s*([\d,]{3,6})\s*元\s*/\s*吨', "元/吨"),
    (r'([\d,]{3,6})\s*元\s*/\s*吨', "元/吨"),
    (r'([\d,]{3,6})\s*美元\s*/\s*吨', "美元/吨"),
    (r'([\d,]{3,6})\s*美金\s*/\s*吨', "美元/吨"),
    (r'\$\s*([\d,]{2,5})\s*/\s*(?:公吨|吨|mt|MT)', "美元/吨"),
    (r'([\d,]{3,6})\s*元\s*/\s*(?:公斤|kg|千克)', "元/公斤"),
]
TREND_PATTERNS = [
    (r'(上涨|下跌|涨|跌|走高|走低|上行|下行|持稳|持平|窄幅)', "方向"),
    (r'([+\-]?\d{1,3}(?:\.\d{1,2})?)\s*%', "幅度"),
]
TREND_CTX = ["上涨", "下跌", "涨超", "跌超", "涨了", "跌了", "上调", "下调", "涨", "跌", "下探", "回落"]
NOISE_WORDS = config.PRICE.get("noise_words", [])


def _norm_date(ds):
    """引擎相对时间（'1 day ago'/'3 days ago'/'X hours ago'）→ YYYY-MM-DD；解析不了则用今天。"""
    dt = config.parse_date(ds)
    return dt.strftime("%Y-%m-%d") if dt else config.today_str()


def _extract_points(docs, item_name, pmin, pmax):
    points = []
    for d in docs:
        text = (d.title + " " + d.snippet).lower()
        if any(w in text for w in NOISE_WORDS):
            continue
        prices = []
        for pat, unit in PRICE_PATTERNS:
            for m in re.finditer(pat, text):
                if len(m.groups()) >= 2 and m.group(2):
                    lo = int(m.group(1).replace(",", ""))
                    hi = int(m.group(2).replace(",", ""))
                    val = str((lo + hi) // 2)
                else:
                    val = m.group(1).replace(",", "")
                prefix = text[max(0, m.start() - 3):m.start()]
                if any(t in prefix for t in TREND_CTX):
                    continue
                try:
                    num = int(val)
                except ValueError:
                    continue
                if num < pmin or num > pmax:
                    continue
                prices.append({"price": val, "unit": unit})
        if not prices:
            continue
        trend, trend_pct = "", ""
        for pat, kind in TREND_PATTERNS:
            m = re.search(pat, text)
            if m:
                if kind == "方向":
                    trend = m.group(1)
                else:
                    trend_pct = m.group(1)
        try:
            # 日度参考价涨跌 >30% 几乎必是「累计/年内」等被误提取，丢弃
            if trend_pct and not (0 < float(trend_pct) <= 30):
                trend_pct = ""
        except ValueError:
            trend_pct = ""
        for p in prices[:3]:
            points.append({
                "item": item_name, "price": p["price"], "unit": p["unit"],
                "trend": trend, "trend_pct": trend_pct,
                "source": d.site, "date": _norm_date(d.date),
                "title": d.title[:50],
            })
    return points


def collect():
    """采集全部价格品种，返回 list[价格点 dict]。"""
    out = []
    for item in config.PRICE_ITEMS:
        q = item.get("query", "")
        pmin, pmax = item.get("min", 0), item.get("max", 10 ** 6)
        docs = []
        docs += serper_engine.search(q, config.PRICE_DAYS, lang="zh")
        docs += tavily_engine.search(q, config.PRICE_DAYS, lang="zh")
        out += _extract_points(docs, item.get("name", ""), pmin, pmax)
    return out
