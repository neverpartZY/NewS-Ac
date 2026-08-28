# -*- coding: utf-8 -*-
"""AI 加工：逐条把候选新闻精炼成结构化条目（中文标题/摘要/分类/细分/重要性/标签）。

fail-soft：LLM 不可用/失败 → 用原标题/摘要兜底，绝不丢条目。
scope 归属：有 scope_hint（来自采集任务维度）则权威采用；无则交 LLM 判定（公众号/源站等）。
"""
import json

import config
from . import llm
from .models import Article, Candidate

SYS = (
    "你是塑料循环经济日报的编辑。把每条候选新闻加工成一条精炼条目，字段如下：\n"
    "- title_zh：中文主标题（若原文为英文，翻译成简体中文；专有名词缩写 PPWR/rPET/PET/EPR 可保留）\n"
    "- summary_zh：80~120 字中文摘要，讲清「发生了什么、数字多少、影响是什么」\n"
    "- category：policy(政策法规)/market(价格市场)/tech(技术标准)/enterprise(企业动态)/global(海外动态)\n"
    "- scope：chemical(化学回收/热解/解聚/气化/水热)、rpet(再生PET/瓶片/食品级/品牌承诺)、general(其他塑料回收)\n"
    "- importance：1~5 整数（政策/龙头事件=4~5，常规行情/快讯=2~3）\n"
    "- tags：2~4 个中文关键词\n"
    "只输出 JSON：{\"results\":[{\"id\":<int>,\"title_zh\":\"\",\"summary_zh\":\"\",\"category\":\"\",\"scope\":\"\",\"importance\":<int>,\"tags\":[\"\"]}]}\n"
    "禁止编造信息，只能基于给出的标题/摘要加工。"
)


def refine(docs):
    """批量精炼。返回 list[Article]。"""
    if not docs:
        return []
    CHUNK = 20
    out = []
    for i in range(0, len(docs), CHUNK):
        chunk = docs[i:i + CHUNK]
        items = [{"id": j, "title": d.title, "snippet": (d.snippet or "")[:200]}
                 for j, d in enumerate(chunk)]
        r = llm.chat_json([
            {"role": "system", "content": SYS},
            {"role": "user", "content": "请加工下面每条候选新闻：\n" + json.dumps(items, ensure_ascii=False)},
        ], max_tokens=4000)
        by_id = {x.get("id"): x for x in (r or {}).get("results", [])} if r else {}
        for j, d in enumerate(chunk):
            out.append(_article(d, by_id.get(j) or {}))
    return out


def _fmt_date(ds):
    """把相对时间（'5 days ago'）归一化成 YYYY-MM-DD；解析不了则原样保留。"""
    dt = config.parse_date(ds)
    return dt.strftime("%Y-%m-%d") if dt else (ds or "")


def _article(d: Candidate, x: dict) -> Article:
    title_zh = x.get("title_zh") or d.title
    summary_zh = x.get("summary_zh") or d.snippet[:120]
    scope = d.scope_hint if d.scope_hint else (x.get("scope") or "general")
    return Article(
        url_hash=d.url_hash,
        title=d.title,
        title_zh=title_zh,
        summary_zh=summary_zh,
        category=x.get("category", "general"),
        scope=scope,
        importance=int(x.get("importance", 3)),
        tags=x.get("tags", []),
        source=d.engine,
        site=d.site,
        url=d.url,
        published_at=_fmt_date(d.date),
        collected_at=config.now_local_str(),
        embedding=d.embedding,
        is_price=False,
    )
