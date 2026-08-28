# -*- coding: utf-8 -*-
"""流水线编排：采集 → 过滤 → 去重 → 加工 → 生成 → 落库 → 推送。"""
import config
from datetime import timedelta

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


ENGINE_KEY_ENV = {"serper": "SERPER_API_KEY", "tavily": "TAVILY_API_KEY"}


def collect(freqs):
    """多引擎采集，并统计各引擎产出（供健康判断，区分「引擎失效」与「无新闻」）。"""
    docs = []
    stats = {}  # engine -> {"queries": n, "docs": n}

    def _track(name, results):
        s = stats.setdefault(name, {"queries": 0, "docs": 0})
        s["queries"] += 1
        s["docs"] += len(results)
        return results

    for t in config.TASKS:
        if not t.get("auto"):
            continue
        if freqs is not None and t.get("freq", "D1") not in freqs:
            continue
        q = t.get("query", "")
        lang = t.get("lang", "zh")
        # P1-2：用任务维度预标注 scope（V4→chemical / V5→rpet），供 refine 权威采用
        hint = scope_hint_from_dim(t.get("dim", ""))
        task_docs = (_track("serper", serper.search(q, config.FRESH_DAYS, lang))
                     + _track("tavily", tavily.search(q, config.FRESH_DAYS, lang)))
        for c in task_docs:
            c.scope_hint = hint
        docs += task_docs
    docs += _track("gzh", gzh.collect(config.FRESH_DAYS))
    docs += _track("site", source_site.collect())
    price_points = price.collect()
    return _collapse(docs), price_points, stats


def _engine_health(stats):
    """引擎健康：有 key 且有查询但 0 产出 → 疑似失效；未配 key → 跳过。"""
    failed, skipped, ok = [], [], []
    for name, s in stats.items():
        if name in ENGINE_KEY_ENV:
            keyed = bool(config.get_key(ENGINE_KEY_ENV[name]))
        elif name == "gzh":
            keyed = bool(gzh._key())
        else:  # site 等衍生通道，随其上游引擎
            keyed = True
        if not keyed:
            skipped.append(name)
        elif s["queries"] > 0 and s["docs"] == 0:
            failed.append(name)
        else:
            ok.append(name)
    return failed, skipped, ok


def _alert_markdown(stats, failed, skipped, date_str):
    """引擎失效告警正文。"""
    lines = ["# ⚠️ 采集异常告警", date_str, "",
             "本轮采集总产出为 0，疑似引擎失效（key 失效 / 配额用尽 / 网络问题），而非当天无新闻。",
             "按旧系统「空转兜底」规则：不生成空日报冒充正常，先告警。", "",
             "## 各引擎状态", "", "| 引擎 | 查询次数 | 产出 | 状态 |", "|---|---|---|---|"]
    for name, s in stats.items():
        st = "疑似失效" if name in failed else ("未配 key" if name in skipped else "正常")
        lines.append(f"| {name} | {s['queries']} | {s['docs']} | {st} |")
    lines += ["", "排查后手动重跑：`python main.py --once`"]
    return "\n".join(lines)


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
    docs, price_points, stats = collect(freqs)
    summary["collected"] = len(docs)
    summary["price_points"] = len(price_points)
    failed, skipped, ok = _engine_health(stats)
    summary["engines"] = {"ok": ok, "failed": failed, "skipped": skipped}
    print(f"[collect] 候选 {len(docs)} 条 / 价格点 {len(price_points)} 个 "
          f"| 引擎 ok={ok} failed={failed} skipped={skipped}")

    # 1.5 空转兜底（旧系统铁律：先判引擎失效，再判无新闻）
    if not docs:
        summary["status"] = "alert_no_collection"
        print("[health] ⚠️ 全部引擎 0 产出，按「引擎失效」处理：发告警，不生成空日报")
        if do_push and not dry_run:  # dry-run 绝不外发
            alert = _alert_markdown(stats, failed, skipped, config.today_str())
            st = push_mod.email.send_alert(f"⚠️ 采集异常告警 · {config.today_str()}", alert)
            print(f"[alert] 邮件告警: {st}")
        return summary

    if failed:
        print(f"[health] ⚠️ 引擎疑似失效（有 key 但 0 产出）: {failed}，本轮日报覆盖可能下降")

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
        _save_push_ledger(date_str, push_results)
        for rname, chans in push_results.items():
            for chan, st in chans.items():
                print(f"[push] {rname} · {chan}: {st.get('status')} {st.get('reason', '')}")

    # 8. 维护：清理 30 天前的已收录条目
    pruned = storage.prune(days=30)
    if pruned:
        summary["pruned"] = pruned
        print(f"[maint] 清理 {pruned} 条 30 天前旧闻")
    return summary


def _save_push_ledger(date_str, push_results):
    """推送状态台账落盘，便于排障（data/push_ledger_<日期>.json）。"""
    import json
    ledger = config.DATA_DIR / f"push_ledger_{date_str}.json"
    ledger.write_text(json.dumps(push_results, ensure_ascii=False, indent=2), encoding="utf-8")


def run_periodic(period, do_push=True):
    """生成周报/月报：从已收录列表取过去 N 天数据，精选提炼（不重新采集）。"""
    days = 7 if period == "weekly" else 30
    since = (config.today_local() - timedelta(days=days)).strftime("%Y-%m-%d")
    articles = storage.load_articles(since_date=since)
    price_points = price.collect()
    date_str = config.today_str()
    names = REPORT_NAMES if period == "weekly" else ["月报"]
    reports = {}
    for rname in names:
        subset = _scope_filter(articles, rname)
        md = report.generate_periodic(rname, subset, price_points, period)
        reports[rname] = md
        out = config.REPORT_DIR / f"{rname}_{date_str}.md"
        out.write_text(md, encoding="utf-8")
        print(f"[{period}] {rname}（{len(subset)} 条）-> {out.name}")
    if do_push:
        push_results = push_mod.push_all(reports, date_str)
        _save_push_ledger(date_str, push_results)
        for rname, chans in push_results.items():
            for chan, st in chans.items():
                print(f"[push] {rname} · {chan}: {st.get('status')} {st.get('reason', '')}")
    return {"period": period, "articles": len(articles), "reports": list(reports.keys())}
