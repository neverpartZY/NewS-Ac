# -*- coding: utf-8 -*-
"""报告生成 = 质量关键：LLM 主编真编辑（少而精），而非模板堆砌。

产出 3 份分报：综合日报 / 化学循环日报 / 再生PET日报。
"""
import config
from . import llm

# scope → 日报归属
SCOPE_TO_REPORT = {
    "chemical": "化学循环日报",
    "rpet": "再生PET日报",
    "general": "综合日报",
}

EDITOR_SYS = (
    "你是「塑料循环经济日报」AI 主编，读者是塑料回收行业的企业客户。\n"
    "请根据下面给出的候选新闻（已去重、已翻译、含中文标题/摘要/分类/重要度/链接/日期），"
    "撰写一份日报。要求：\n"
    "1. 全程简体中文，不出现英文正文；专有名词（PPWR/rPET/PET/EPR）可保留。\n"
    "2. 少而精，不做信息堆砌：每个板块只保留当日最重要、最有实质价值的 1~3 条；"
    "核心板块（企业动态/资本投融/政策法规）最多 5 条。当日某板块无重要增量就省略该板块，不要写空话。\n"
    "3. 结构（有内容才显示）：\n"
    "   # ♻️ 塑料循环经济日报（标题按报告类型写）\n"
    "   <日期>\n"
    "   ## 一、今日核心叙事\n"
    "   （挑当日最重要的 1~3 件事，写成「标题：摘要」连贯叙事句，禁止用项目符号罗列标题）\n"
    "   ## 企业动态 / 资本投融 / 政策法规 / 价格行情 / 技术标准 / 前沿研究 / 海外动态 …\n"
    "   每条格式：\n"
    "   1. **中文标题**\n"
    "      100~200 字摘要（有实质信息：发生了什么、数字、影响）\n"
    "      [查看原文](完整URL) · YYYY-MM-DD日期\n"
    "4. 价格行情表直接采用我给的参考价格表，保留全部列（品种/参考价/单位/趋势/来源/日期），不要删列。\n"
    "5. 铁律：每条必须基于给定候选，不得编造信息/数据/URL；无链接的条目不用；"
    "当日确实无新增就写「今日无新增」；日期一律写候选给的「YYYY-MM-DD」，不得改成「X天前」等相对时间。\n"
    "5. 直接输出 Markdown 正文，不要任何解释性前言/后记。"
)


def _format_candidates(articles):
    lines = []
    for i, a in enumerate(articles):
        lines.append(
            f"[{i}] 标题:{a.title_zh} | 分类:{a.category} | "
            f"重要度:{a.importance} | 来源:{a.site} | "
            f"日期:{a.published_at}\n    摘要:{a.summary_zh}\n    URL:{a.url}"
        )
    return "\n".join(lines)


def _price_table(price_points):
    if not price_points:
        return ""
    lines = ["## 价格行情", "", "| 品种 | 参考价 | 单位 | 趋势 | 来源 | 日期 |", "|---|---|---|---|---|---|"]
    seen = set()
    for p in price_points:
        date = p.get("date", "")
        key = (p.get("item"), p.get("price"), p.get("source"), date)
        if key in seen:
            continue
        seen.add(key)
        trend = p.get("trend", "")
        if p.get("trend_pct"):
            trend += f" {p['trend_pct']}%"
        lines.append(f"| {p.get('item', '')} | {p.get('price', '')} | {p.get('unit', '')} | {trend} | {p.get('source', '')} | {date} |")
    lines.append("\n> 价格数据来源于公开搜索渠道，多源交叉印证，有出处可核对。")
    return "\n".join(lines)


def generate(report_name, articles, price_points=None):
    """生成一份日报 markdown。articles 已按 scope 过滤好。"""
    date_str = config.today_str()
    if not articles and not price_points:
        return f"# ♻️ {report_name}\n{date_str}\n\n今日无新增。\n"
    # 按重要度排序，输入控制在上限内（LLM 只做精选，不做全量罗列）
    arts = sorted(articles, key=lambda a: -a.importance)[:40]
    cands = _format_candidates(arts)
    price_md = _price_table(price_points or [])

    user = (
        f"报告类型：{report_name}\n日期：{date_str}\n\n"
        f"候选新闻（已去重，供你精选）：\n{cands}\n\n"
        f"参考价格表（直接采用，可整合进日报价格板块）：\n{price_md or '（今日无价格数据）'}\n"
    )
    text = llm.chat([
        {"role": "system", "content": EDITOR_SYS},
        {"role": "user", "content": user},
    ], temperature=0.3, max_tokens=4000)
    if isinstance(text, dict) or not text.strip():
        return f"# ♻️ {report_name}\n{date_str}\n\n（生成失败）\n\n{cands}\n"
    return text.strip()
