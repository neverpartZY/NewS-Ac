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


def clean_price_points(points, days=None):
    """价格点收敛（用户 2026-08-28 定的三条规则，保持多源对照、去噪）：

    1. 只留最近 PRICE_DAYS(2) 天的价格点，过期直接丢；
    2. 同品种取中位数，偏离 >30% 的按离群值丢弃（解决 3900 与 7922 并存）；
    3. 每品种每天最多 2 行，且同一天不重复同一来源。
    """
    days = config.PRICE_DAYS if days is None else days
    today = config.today_local()
    # 规则1：时效
    recent = []
    for p in points:
        dt = config.parse_date(p.get("date", ""))
        if dt and (today - dt).days <= days:
            recent.append(p)
    # 规则2：离群值（按品种分组）
    by_item = {}
    for p in recent:
        by_item.setdefault(p.get("item", ""), []).append(p)
    survivors = []
    for pts in by_item.values():
        pairs = []
        for p in pts:
            try:
                pairs.append((p, float(str(p.get("price", "")).replace(",", ""))))
            except (ValueError, TypeError):
                continue
        if not pairs:
            continue
        vals = sorted(v for _, v in pairs)
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        if median > 0:
            pairs = [(p, v) for p, v in pairs if abs(v - median) / median <= 0.30]
        # 规则3：每品种每天最多 2 行不同来源（日期新优先）
        per_day = {}
        for p, _ in sorted(pairs, key=lambda pv: pv[0].get("date", ""), reverse=True):
            bucket = per_day.setdefault(p.get("date", ""), [])
            if len(bucket) < 2 and p.get("source") not in {b.get("source") for b in bucket}:
                bucket.append(p)
        for bucket in per_day.values():
            survivors.extend(bucket)
    return survivors


def collect():
    """采集全部价格品种，返回收敛后的 list[价格点 dict]。"""
    out = []
    for item in config.PRICE_ITEMS:
        q = item.get("query", "")
        pmin, pmax = item.get("min", 0), item.get("max", 10 ** 6)
        docs = []
        docs += serper_engine.search(q, config.PRICE_DAYS, lang="zh")
        docs += tavily_engine.search(q, config.PRICE_DAYS, lang="zh")
        out += _extract_points(docs, item.get("name", ""), pmin, pmax)
    return clean_price_points(out)
