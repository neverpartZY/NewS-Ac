# -*- coding: utf-8 -*-
"""过滤层：时效(3天) + 中文检测 + 硬噪声词 + LLM 主题相关性。

三层由快到慢：硬噪声词 → 时效/stale → LLM 相关性。词表与 stale 判定复用旧系统踩坑成果。
"""
import json
import re

import config
from . import llm
from .models import Candidate

# ---- stale 判定词表（复用旧系统） ----
STALE_KEYWORDS_STRONG = ("盘点", "回顾", "往期", "旧闻", "合集", "历史",
                         "周报", "月报", "日报", "周评", "周刊",
                         "roundup", "recap", "weekly digest")
STALE_KEYWORDS_WEAK = ("年度", "上周", "上月", "上半年", "下半年",
                       "一季度", "二季度", "三季度", "四季度",
                       "财报", "年报", "中报", "半年报", "季报", "旬报", "总结", "汇总")
STALE_CONTEXT_WORDS = ("盘点", "回顾", "报告", "财报", "走势", "合集", "往期", "历史", "旧闻")
FRESH_ACTION_WORDS = ("签约", "披露", "官宣", "发布", "获批", "落地", "完成",
                      "获得", "获", "新签", "达成", "启动", "通过", "敲定",
                      "融资", "宣布", "上线", "投产")

_CJK_RE = re.compile(r'[一-鿿]')


def has_cjk(text):
    return bool(_CJK_RE.search(text or ""))


def is_stale(title, snippet=""):
    """分级判 stale：强信号裸词命中即丢；弱信号 + 盘点词才丢；时间词 + 披露动词放行。"""
    text = title + " " + snippet
    low = text.lower()
    if any(k in low for k in STALE_KEYWORDS_STRONG):
        return True
    time_word_hit = any(w in text for w in ("上周", "上月", "年度", "季度", "上半年", "下半年"))
    if time_word_hit and any(a in text for a in FRESH_ACTION_WORDS):
        return False
    for w in STALE_KEYWORDS_WEAK:
        if w in text and any(c in text for c in STALE_CONTEXT_WORDS):
            return True
    return False


def date_in_window(ds, days):
    dt = config.parse_date(ds)
    if dt is None:
        return False, False
    return True, (config.today_local() - dt).days <= days


def date_filter(docs, days):
    """时效硬过滤：stale 丢弃、超窗口丢弃、无日期降级保留（nd_date=True）。

    日期字段为空时，尝试从 URL 提取日期再判时效，减少「空日期旧闻」漏网。
    """
    kept, dropped = [], 0
    for d in docs:
        title = (d.title or "").strip()
        url = (d.url or "").strip()
        if is_stale(title, d.snippet):
            dropped += 1
            continue
        ds = (d.date or "").strip()
        if not ds and url:
            ds = config.date_from_url(url)
            if ds:
                d.date = ds  # 回填从 URL 提取的日期
        ok, in_window = date_in_window(ds, days)
        if ok and in_window:
            d.nd_date = False
            kept.append(d)
            continue
        if ok and not in_window:
            dropped += 1
            continue
        # 无日期：时效不可证。引擎按 7 天窗口返回，放行会放进旧闻——宁缺毋滥，直接丢
        dropped += 1
    return kept, dropped


def hard_noise_filter(docs):
    """硬噪声词命中即丢（纯期货/财经行情跑偏内容）；营销页/官网首页过滤。"""
    kept = []
    for d in docs:
        text = (d.title + " " + d.snippet).lower()
        title = (d.title or "").strip().lower()
        raw_title = (d.title or "").strip()
        if any(w in text for w in config.HARD_NOISE_WORDS):
            continue
        has_plastic = any(w in text for w in config.DOMAIN_WORDS)
        has_noise = any(w in text for w in config.NOISE_WORDS)
        if has_noise and not has_plastic:
            continue
        if any(w in title for w in config.CONTENT_NOISE_WORDS):
            continue
        if len(raw_title) <= 6 and raw_title and not any(c.isascii() for c in raw_title):
            continue
        kept.append(d)
    return kept


def relevance_judge(docs, threshold=None):
    """LLM 主题相关性打分。fail-soft：LLM 不可用/失败 → 关键词兜底，绝不静默丢弃。"""
    threshold = config.RELEVANCE_THRESHOLD if threshold is None else threshold
    if not docs:
        return []
    if not llm.available():
        # 降级：关键词兜底（含领域词即保留），并标注降级
        kept = [d for d in docs if any(w in (d.title + " " + d.snippet).lower()
                                       for w in config.DOMAIN_WORDS)]
        for d in kept:
            d.score = 0.8
            d.reason = "关键词兜底（LLM 不可用）"
        return kept

    sys_prompt = (
        "你是塑料回收行业的新闻相关性判断助手。判断每条候选新闻是否与「塑料回收」主题相关"
        "（涵盖：废塑料回收、再生塑料、再生PET/rPET、化学回收/热解/解聚、PPWR/EPR政策、"
        "再生料价格、塑料循环利用企业/项目/融资）。纯化工期货/财经行情、无关行业内容判为不相关。\n"
        "只输出 JSON：{\"results\":[{\"id\":<int>,\"relevant\":true/false,\"score\":0到1,\"reason\":\"一句话\"}]}"
    )
    kept = []
    CHUNK = 20
    for i in range(0, len(docs), CHUNK):
        chunk = docs[i:i + CHUNK]
        items = [{"id": j, "title": d.title, "snippet": (d.snippet or "")[:200]}
                 for j, d in enumerate(chunk)]
        out = llm.chat_json([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "请判断下面每一条是否与塑料回收相关：\n" + json.dumps(items, ensure_ascii=False)},
        ], max_tokens=3000)
        if not out or "results" not in out:
            # 判不出 → 保守保留，标注降级（后续环节兜底）
            for d in chunk:
                d.score = 0.6
                d.reason = "LLM 判不出，保守保留"
            kept.extend(chunk)
            continue
        by_id = {r.get("id"): r for r in out.get("results", [])}
        for j, d in enumerate(chunk):
            r = by_id.get(j) or {}
            if r.get("relevant") and (r.get("score") or 0) >= threshold:
                d.score = r.get("score", 0.6)
                d.reason = r.get("reason", "")
                kept.append(d)
    return kept
