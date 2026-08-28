# -*- coding: utf-8 -*-
"""流水线编排：采集 → 过滤 → 去重 → 加工 → 生成 → 落库 → 推送。"""
import config
from . import dedup, filter as f, linkcheck, refine, report, storage
from . import push as push_mod
from .engines import gzh, price, serper, source_site, tavily
from .models import scope_hint_from_dim

REPORT_NAMES = ["综合日报", "化学循环日报", "再生PET日报"]


def _collapse(docs):
    """同轮 URL 去重：同一 URL 只保留一条（优先有 snippet 的）。"""
    seen = {}
    for d in docs:
        u = (d.url or "").strip()
        if not u:
            continue
        if u in seen:
            if d.snippet and not seen[u].snippet:
                seen[u] = d
        else:
            seen[u] = d
    return list(seen.values())


def collect(freqs):
    """多引擎采集。freqs: 要跑的 task 频率集合（如 {'D1'}），None=全部 auto。"""
    docs = []
    for t in config.TASKS:
        if not t.get("auto"):
            continue
        if freqs is not None and t.get("freq", "D1") not in freqs:
            continue
        q = t.get("query", "")
        lang = t.get("lang", "zh")
        # P1-2：用任务维度预标注 scope（V4→chemical / V5→rpet），供 refine 权威采用
        hint = scope_hint_from_dim(t.get("dim", ""))
        task_docs = serper.search(q, config.FRESH_DAYS, lang) + tavily.search(q, config.FRESH_DAYS, lang)
        for c in task_docs:
            c.scope_hint = hint
        docs += task_docs
    docs += gzh.collect(config.FRESH_DAYS)
    docs += source_site.collect()
    price_points = price.collect()
    return _collapse(docs), price_points


def _scope_filter(articles, report_name):
    if report_name == "化学循环日报":
        return [a for a in articles if a.scope == "chemical"]
    if report_name == "再生PET日报":
        return [a for a in articles if a.scope == "rpet"]
    return articles  # 综合 = 全部


def run(dry_run=False, do_push=True, freqs=None):
    """跑一轮完整流水线。返回汇总 dict。"""
    summary = {}
    # 1. 采集
    docs, price_points = collect(freqs)
    summary["collected"] = len(docs)
    summary["price_points"] = len(price_points)
    print(f"[collect] 候选 {len(docs)} 条 / 价格点 {len(price_points)} 个")

    if dry_run:
        summary["docs"] = docs
        summary["price_points_data"] = price_points
        return summary

    # 2. 过滤
    docs = f.hard_noise_filter(docs)
    docs, dropped = f.date_filter(docs, config.FRESH_DAYS)
    docs = f.relevance_judge(docs)
    summary["after_filter"] = len(docs)
    print(f"[filter] 通过 {len(docs)} 条（时效/stale 丢弃 {dropped}）")

    # 3. 去重
    keep, dups, skipped = dedup.dedup(docs)
    summary["new"] = len(keep)
    summary["dups"] = len(dups) + skipped
    print(f"[dedup] 新收录 {len(keep)} / 重复 {len(dups) + skipped}（语义 {len(dups)}，URL {skipped}）")

    # 3.5 链接探活（去重后、加工前，只丢 404/410 死链）
    keep, dead_links = linkcheck.drop_dead(keep)
    summary["dead_links"] = len(dead_links)
    print(f"[linkcheck] 死链丢弃 {len(dead_links)}")

    # 4. 加工
    articles = refine.refine(keep)
    # 5. 落库
    for a in articles:
        storage.insert(a)
    summary["stored"] = storage.count()

    # 6. 生成 3 份分报
    date_str = config.today_str()
    reports = {}
    for rname in REPORT_NAMES:
        subset = _scope_filter(articles, rname)
        md = report.generate(rname, subset, price_points)
        reports[rname] = md
        out = config.REPORT_DIR / f"{rname}_{date_str}.md"
        out.write_text(md, encoding="utf-8")
        print(f"[report] {rname} -> {out}")

    # 7. 推送
    if do_push:
        push_results = push_mod.push_all(reports, date_str)
        summary["push"] = push_results
        for rname, chans in push_results.items():
            for chan, st in chans.items():
                print(f"[push] {rname} · {chan}: {st.get('status')} {st.get('reason', '')}")
    return summary
